import { useState, useRef } from "react";
import { Card, Input, Button, Typography, Space, Tag, Divider } from "antd";
import {
  SendOutlined,
  UserOutlined,
  RobotOutlined,
} from "@ant-design/icons";
import { query } from "../services/api";
import type { QueryResponse } from "../types/api";

const { Text, Paragraph } = Typography;

const categoryColor: Record<string, string> = {
  dimension: "purple",
  metric: "blue",
  fact: "green",
  other: "default",
};

export default function NLQuery() {
  const [question, setQuestion] = useState("");
  const [_result, setResult] = useState<QueryResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [history, setHistory] = useState<{ q: string; r: QueryResponse }[]>([]);
  const scrollRef = useRef<HTMLDivElement>(null);

  const handleQuery = async () => {
    if (!question.trim()) return;
    setLoading(true);
    try {
      const res = await query({ question: question.trim() });
      setResult(res.data);
      setHistory((prev) => [...prev, { q: question, r: res.data }]);
      setQuestion("");
    } catch {
      // Error handled by interceptor
    } finally {
      setLoading(false);
    }
  };

  const renderScore = (score: number) => {
    const percent = Math.round(score * 100);
    return (
      <div style={{ width: 60 }}>
        <div
          style={{
            height: 6,
            background: "#f0f0f0",
            borderRadius: 3,
            overflow: "hidden",
          }}
        >
          <div
            style={{
              height: "100%",
              width: `${percent}%`,
              background: percent > 70 ? "#52c41a" : percent > 40 ? "#faad14" : "#ff4d4f",
              borderRadius: 3,
            }}
          />
        </div>
        <Text style={{ fontSize: 12 }}>{percent}%</Text>
      </div>
    );
  };

  return (
    <div>
      <Typography.Title level={3}>自然语言查询</Typography.Title>
      <Typography.Paragraph type="secondary">
        用自然语言提问，AI 将基于数据库语义层回答您的问题
      </Typography.Paragraph>

      {/* Input */}
      <Card>
        <Space style={{ width: "100%" }} size="middle">
          <Input
            size="large"
            placeholder="请输入您的问题，例如：查询每个用户的订单数量"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onPressEnter={handleQuery}
            disabled={loading}
          />
          <Button
            type="primary"
            icon={<SendOutlined />}
            onClick={handleQuery}
            loading={loading}
            disabled={!question.trim()}
            size="large"
          >
            发送
          </Button>
        </Space>
      </Card>

      {/* History */}
      <div ref={scrollRef} style={{ marginTop: 24 }}>
        {history.map((item, idx) => (
          <Card
            key={idx}
            style={{ marginBottom: 16 }}
            title={
              <Space>
                <UserOutlined />
                <Text>{item.q}</Text>
              </Space>
            }
          >
            <Space direction="vertical" style={{ width: "100%" }}>
              {/* Answer */}
              <div style={{ background: "#f6ffed", padding: 12, borderRadius: 6 }}>
                <Space>
                  <RobotOutlined style={{ color: "#52c41a" }} />
                  <Text strong>回答：</Text>
                </Space>
                <Paragraph style={{ marginTop: 8, marginBottom: 0 }}>
                  {item.r.answer || (item.r.has_error ? item.r.error_message : "暂无回答")}
                </Paragraph>
              </div>

              {/* Relevant Fields */}
              {item.r.relevant_fields.length > 0 && (
                <>
                  <Divider style={{ margin: 8 }}>相关字段 ({item.r.relevant_fields.length})</Divider>
                  {item.r.relevant_fields.map((f, i) => (
                    <div key={i} style={{ padding: 8, background: "#fafafa", borderRadius: 4, marginBottom: 4 }}>
                      <Space style={{ width: "100%", justifyContent: "space-between" }}>
                        <Space>
                          <Text strong>{f.column_name}</Text>
                          <Text type="secondary">（{f.table_name}）</Text>
                          {f.chinese_name && <Tag>{f.chinese_name}</Tag>}
                          <Tag color={categoryColor[f.data_category] || "default"}>{f.data_category}</Tag>
                        </Space>
                        {renderScore(f.relevance_score)}
                      </Space>
                      {f.business_definition && (
                        <Text type="secondary" style={{ fontSize: 12 }}>
                          {f.business_definition}
                        </Text>
                      )}
                    </div>
                  ))}
                </>
              )}

              {/* Relevant Tables */}
              {item.r.relevant_tables.length > 0 && (
                <>
                  <Divider style={{ margin: 8 }}>相关表 ({item.r.relevant_tables.length})</Divider>
                  {item.r.relevant_tables.map((t, i) => (
                    <div key={i} style={{ padding: 8, background: "#fafafa", borderRadius: 4, marginBottom: 4 }}>
                      <Space style={{ width: "100%", justifyContent: "space-between" }}>
                        <Space>
                          <Text strong>{t.table_name}</Text>
                          {t.chinese_name && <Tag>{t.chinese_name}</Tag>}
                          <Tag color={categoryColor[t.data_category] || "default"}>{t.data_category}</Tag>
                        </Space>
                        {renderScore(t.relevance_score)}
                      </Space>
                      {t.business_definition && (
                        <Text type="secondary" style={{ fontSize: 12 }}>
                          {t.business_definition}
                        </Text>
                      )}
                    </div>
                  ))}
                </>
              )}
            </Space>
          </Card>
        ))}
      </div>
    </div>
  );
}
