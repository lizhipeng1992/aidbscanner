import { useState, useEffect } from "react";
import { Card, Row, Col, Button, Space, Tag, Typography, message, Spin, Divider } from "antd";
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  ScanOutlined,
} from "@ant-design/icons";
import { getHealth, getDatabases, fullScan } from "../services/api";
import type { HealthResponse, ScanResult } from "../types/api";

const { Title, Text, Paragraph } = Typography;

export default function Dashboard() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [databases, setDatabases] = useState<string[]>([]);
  const [selectedDb, setSelectedDb] = useState<string>("");
  const [scanResult, setScanResult] = useState<ScanResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [healthLoading, setHealthLoading] = useState(true);
  const [dbLoading, setDbLoading] = useState(false);

  useEffect(() => {
    fetchHealth();
  }, []);

  useEffect(() => {
    if (health) {
      fetchDatabases();
    }
  }, [health]);

  const fetchHealth = async () => {
    try {
      setHealthLoading(true);
      const res = await getHealth();
      setHealth(res.data);
    } catch {
      message.error("无法连接后端服务，请确保后端已启动");
    } finally {
      setHealthLoading(false);
    }
  };

  const fetchDatabases = async () => {
    try {
      setDbLoading(true);
      const res = await getDatabases();
      setDatabases(res.data.databases);
    } catch {
      // Silently fail - databases will be empty
    } finally {
      setDbLoading(false);
    }
  };

  const handleScan = async () => {
    if (!selectedDb) {
      message.warning("请先选择数据库");
      return;
    }
    setLoading(true);
    setScanResult(null);
    try {
      const res = await fullScan({ db_name: selectedDb });
      setScanResult(res.data);
      message.success("扫描完成");
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "扫描失败";
      message.error(msg);
    } finally {
      setLoading(false);
    }
  };

  const statusTag = (status: string) => {
    if (status === "connected") return <Tag color="green">已连接</Tag>;
    if (status.startsWith("error")) return <Tag color="red">错误</Tag>;
    return <Tag color="orange">未知</Tag>;
  };

  if (healthLoading) {
    return (
      <div style={{ textAlign: "center", padding: 48 }}>
        <Spin size="large" />
      </div>
    );
  }

  return (
    <div>
      <Title level={3}>仪表盘</Title>
      <Paragraph type="secondary">查看系统状态、选择数据库并开始扫描</Paragraph>

      {/* Health Status */}
      <Row gutter={[16, 16]}>
        <Col span={12}>
          <Card size="small" title="数据库连接">
            <Space>
              {health?.database === "connected" ? (
                <CheckCircleOutlined style={{ color: "#52c41a" }} />
              ) : (
                <CloseCircleOutlined style={{ color: "#ff4d4f" }} />
              )}
              <Text>{health?.database || "未检查"}</Text>
              {statusTag(health?.database ?? "")}
            </Space>
          </Card>
        </Col>
        <Col span={12}>
          <Card size="small" title="LLM 连接">
            <Space>
              {health?.llm === "connected" ? (
                <CheckCircleOutlined style={{ color: "#52c41a" }} />
              ) : (
                <CloseCircleOutlined style={{ color: "#ff4d4f" }} />
              )}
              <Text>{health?.llm || "未检查"} ({health?.llm_provider})</Text>
              {statusTag(health?.llm ?? "")}
            </Space>
          </Card>
        </Col>
      </Row>

      <Divider />

      {/* Scan Controls */}
      <Card size="small" title="数据库扫描">
        <Space direction="vertical" style={{ width: "100%" }} size="middle">
          <div>
            <Text strong>选择数据库：</Text>
            <select
              value={selectedDb}
              onChange={(e) => setSelectedDb(e.target.value)}
              disabled={dbLoading || !databases.length}
              style={{
                marginLeft: 8,
                padding: "4px 12px",
                borderRadius: 6,
                border: "1px solid #d9d9d9",
                fontSize: 14,
                minWidth: 200,
              }}
            >
              <option value="">-- 请选择 --</option>
              {databases.map((db) => (
                <option key={db} value={db}>
                  {db}
                </option>
              ))}
            </select>
            {dbLoading && <Text type="secondary" style={{ marginLeft: 8 }}><Spin size="small" /></Text>}
          </div>

          <Button
            type="primary"
            icon={<ScanOutlined />}
            onClick={handleScan}
            loading={loading}
            disabled={!selectedDb}
            size="large"
          >
            开始扫描
          </Button>
        </Space>
      </Card>

      {/* Scan Results */}
      {scanResult && (
        <>
          <Divider />
          <Card size="small" title="扫描结果">
            <Space direction="vertical" style={{ width: "100%" }}>
              <div>
                <Tag color="blue">{scanResult.database}</Tag>
                <Text>共扫描 {scanResult.tables.length} 张表</Text>
              </div>
              {scanResult.tables.map((t) => (
                <div key={t.table_name} style={{ padding: "8px 0", borderTop: "1px solid #f0f0f0" }}>
                  <Text strong>{t.table_name}</Text>
                  {t.chinese_name && <Text type="secondary" style={{ marginLeft: 8 }}>{t.chinese_name}</Text>}
                  <Tag>{t.data_category}</Tag>
                  <div style={{ marginTop: 4, paddingLeft: 16 }}>
                    {t.fields.map((f) => (
                      <div key={f.column_name} style={{ marginBottom: 4 }}>
                        <Text>{f.column_name}</Text>
                        {f.chinese_name && (
                          <Text type="secondary" style={{ marginLeft: 4 }}>（{f.chinese_name}）</Text>
                        )}
                        <Tag style={{ marginLeft: 8, fontSize: 12 }}>{f.data_category}</Tag>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
              {scanResult.relationships.length > 0 && (
                <div>
                  <Text strong>发现 {scanResult.relationships.length} 个表关系</Text>
                </div>
              )}
            </Space>
          </Card>
        </>
      )}
    </div>
  );
}
