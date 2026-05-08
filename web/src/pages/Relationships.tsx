import { useState, useEffect } from "react";
import { Card, Table, Tag, Typography, Space, Select, Button, message } from "antd";
import {
  ReloadOutlined,
  CheckCircleOutlined,
} from "@ant-design/icons";
import { getDatabases, discoverRelationships, verifyRelationship } from "../services/api";
import type { RelationshipResponse } from "../types/api";

const { Text } = Typography;

export default function Relationships() {
  const [databases, setDatabases] = useState<string[]>([]);
  const [selectedDb, setSelectedDb] = useState<string>("");
  const [relationships, setRelationships] = useState<RelationshipResponse[]>([]);
  const [loading, setLoading] = useState(false);
  const [verifying, setVerifying] = useState<string | null>(null);
  const [dbLoading, setDbLoading] = useState(true);

  useEffect(() => {
    fetchDatabases();
  }, []);

  const fetchDatabases = async () => {
    try {
      setDbLoading(true);
      const res = await getDatabases();
      setDatabases(res.data.databases);
      if (res.data.databases.length > 0) {
        setSelectedDb(res.data.databases[0]);
      }
    } catch {
      message.error("无法获取数据库列表");
    } finally {
      setDbLoading(false);
    }
  };

  const handleDiscover = async () => {
    if (!selectedDb) {
      message.warning("请先选择数据库");
      return;
    }
    setLoading(true);
    try {
      const res = await discoverRelationships(selectedDb);
      setRelationships(res.data);
      message.success(`发现 ${res.data.length} 个关系`);
    } catch {
      message.error("发现关系失败");
    } finally {
      setLoading(false);
    }
  };

  const handleVerify = async (rel: RelationshipResponse) => {
    setVerifying(`${rel.source_table}.${rel.source_column}->${rel.target_table}.${rel.target_column}`);
    try {
      await verifyRelationship({
        db_name: selectedDb,
        source_table: rel.source_table,
        source_column: rel.source_column,
        target_table: rel.target_table,
        target_column: rel.target_column,
      });
      handleDiscover(); // Refresh
      message.success("关系验证完成");
    } catch {
      message.error("关系验证失败");
    } finally {
      setVerifying(null);
    }
  };

  const rateColor = (rate: number) => {
    if (rate >= 0.95) return "#52c41a";
    if (rate >= 0.7) return "#faad14";
    return "#ff4d4f";
  };

  const columns = [
    {
      title: "源表",
      dataIndex: "source_table",
      key: "source_table",
      width: 120,
    },
    {
      title: "源字段",
      dataIndex: "source_column",
      key: "source_column",
      width: 120,
    },
    {
      title: "目标表",
      dataIndex: "target_table",
      key: "target_table",
      width: 120,
    },
    {
      title: "目标字段",
      dataIndex: "target_column",
      key: "target_column",
      width: 120,
    },
    {
      title: "匹配率",
      dataIndex: "match_rate",
      key: "match_rate",
      width: 100,
      render: (v: number) => (
        <Text strong style={{ color: rateColor(v) }}>
          {(v * 100).toFixed(1)}%
        </Text>
      ),
    },
    {
      title: "验证状态",
      dataIndex: "verified",
      key: "verified",
      width: 100,
      render: (v: boolean) =>
        v ? (
          <Tag color="green">
            <CheckCircleOutlined /> 已验证
          </Tag>
        ) : (
          <Tag color="orange">未验证</Tag>
        ),
    },
    {
      title: "操作",
      key: "action",
      width: 100,
      render: (_: unknown, record: RelationshipResponse) => (
        <Button
          size="small"
          type="link"
          loading={verifying === `${record.source_table}.${record.source_column}->${record.target_table}.${record.target_column}`}
          onClick={() => handleVerify(record)}
        >
          验证
        </Button>
      ),
    },
  ];

  return (
    <div>
      <Typography.Title level={3}>表关系</Typography.Title>
      <Space style={{ marginBottom: 16 }}>
        <Select
          value={selectedDb}
          onChange={setSelectedDb}
          style={{ width: 250 }}
          placeholder="选择数据库"
          loading={dbLoading}
        >
          {databases.map((db) => (
            <Select.Option key={db} value={db}>{db}</Select.Option>
          ))}
        </Select>
        <Button type="primary" icon={<ReloadOutlined />} onClick={handleDiscover} loading={loading}>
          发现关系
        </Button>
      </Space>

      <Card size="small" loading={loading}>
        {relationships.length === 0 && !loading ? (
          <div style={{ textAlign: "center", padding: 48, color: "#999" }}>
            <ReloadOutlined style={{ fontSize: 32 }} />
            <p style={{ marginTop: 8 }}>点击"发现关系"开始分析</p>
          </div>
        ) : (
          <Table
            rowKey={(r) => `${r.source_table}.${r.source_column}->${r.target_table}.${r.target_column}`}
            columns={columns}
            dataSource={relationships}
            pagination={{ pageSize: 20 }}
          />
        )}
      </Card>
    </div>
  );
}
