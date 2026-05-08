import { useState, useEffect } from "react";
import {
  Table,
  Card,
  Tag,
  Typography,
  Space,
  Button,
  message,
  Modal,
  Form,
  Input,
  Select,
  Divider,
} from "antd";
import {
  CheckOutlined,
  CloseOutlined,
  EditOutlined,
  ReloadOutlined,
} from "@ant-design/icons";
import {
  getPendingReviews,
  submitReview,
  rejectReview,
  modifyReview,
} from "../services/api";
import type { ReviewPendingItem } from "../types/api";

const { Text } = Typography;

const categoryColor: Record<string, string> = {
  dimension: "purple",
  metric: "blue",
  fact: "green",
  other: "default",
};

export default function ReviewQueue() {
  const [pendingFields, setPendingFields] = useState<ReviewPendingItem[]>([]);
  const [total, setTotal] = useState(0);
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([]);
  const [loading, setLoading] = useState(false);
  const [detailField, setDetailField] = useState<ReviewPendingItem | null>(null);
  const [showDetail, setShowDetail] = useState(false);
  const [showModify, setShowModify] = useState(false);
  const [form] = Form.useForm();
  const [submitLoading, setSubmitLoading] = useState<string | null>(null);

  const fetchPending = async () => {
    setLoading(true);
    try {
      const res = await getPendingReviews();
      setPendingFields(res.data.pending_fields);
      setTotal(res.data.total);
    } catch {
      message.error("获取待审核列表失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchPending();
  }, []);

  const handleFieldClick = (record: ReviewPendingItem) => {
    setDetailField(record);
    setShowDetail(true);
  };

  const handleSubmit = async (fieldId: string) => {
    setSubmitLoading(fieldId);
    try {
      await submitReview({ field_id: fieldId, calibrated_by: "admin" });
      message.success("审核通过");
      fetchPending();
      if (showDetail) setShowDetail(false);
    } catch {
      message.error("审核失败");
    } finally {
      setSubmitLoading(null);
    }
  };

  const handleReject = async (fieldId: string) => {
    setSubmitLoading(fieldId);
    try {
      await rejectReview({ field_id: fieldId, reason: "审核拒绝" });
      message.success("已拒绝");
      fetchPending();
      if (showDetail) setShowDetail(false);
    } catch {
      message.error("拒绝失败");
    } finally {
      setSubmitLoading(null);
    }
  };

  const handleModifySubmit = async () => {
    if (!detailField) return;
    try {
      const values = await form.validateFields();
      await modifyReview({
        field_id: detailField.id,
        calibrated_by: "admin",
        modifications: {
          chinese_name: values.chinese_name,
          business_definition: values.business_definition,
          data_category: values.data_category,
        },
      });
      message.success("修改成功");
      setShowModify(false);
      setShowDetail(false);
      fetchPending();
    } catch {
      message.error("修改失败");
    }
  };

  const batchSubmit = async () => {
    if (selectedRowKeys.length === 0) {
      message.warning("请选择要审核的字段");
      return;
    }
    for (const key of selectedRowKeys) {
      const field = pendingFields.find((f) => f.id === key);
      if (field) {
        await handleSubmit(field.id);
      }
    }
    setSelectedRowKeys([]);
  };

  const columns = [
    {
      title: "表名",
      dataIndex: "table_name",
      key: "table_name",
      width: 150,
    },
    {
      title: "列名",
      dataIndex: "column_name",
      key: "column_name",
      width: 150,
    },
    {
      title: "类型",
      dataIndex: "data_type",
      key: "data_type",
      width: 120,
    },
    {
      title: "中文名",
      dataIndex: "chinese_name",
      key: "chinese_name",
      render: (v: string) => v || <Text type="secondary">未定义</Text>,
    },
    {
      title: "分类",
      dataIndex: "data_category",
      key: "data_category",
      width: 100,
      render: (v: string) => (
        <Tag color={categoryColor[v] || "default"}>{v}</Tag>
      ),
    },
    {
      title: "操作",
      key: "action",
      width: 200,
      render: (_: unknown, record: ReviewPendingItem) => (
        <Space>
          <Button
            size="small"
            type="primary"
            icon={<CheckOutlined />}
            loading={submitLoading === record.id}
            onClick={() => handleSubmit(record.id)}
          >
            通过
          </Button>
          <Button
            size="small"
            danger
            icon={<CloseOutlined />}
            loading={submitLoading === record.id}
            onClick={() => handleReject(record.id)}
          >
            拒绝
          </Button>
        </Space>
      ),
    },
  ];

  return (
    <div>
      <Space style={{ marginBottom: 16 }}>
        <Text strong>待审核队列</Text>
        <Tag color="orange">共 {total} 条</Tag>
        <Button icon={<ReloadOutlined />} onClick={fetchPending}>
          刷新
        </Button>
        <Button type="primary" onClick={batchSubmit} disabled={selectedRowKeys.length === 0}>
          批量通过 ({selectedRowKeys.length})
        </Button>
      </Space>

      <Card size="small">
        <Table
          rowKey="id"
          columns={columns}
          dataSource={pendingFields}
          rowSelection={{
            selectedRowKeys,
            onChange: (keys) => setSelectedRowKeys(keys),
          }}
          loading={loading}
          pagination={{ pageSize: 20 }}
          onRow={(record) => ({
            style: { cursor: "pointer" },
            onClick: () => handleFieldClick(record),
          })}
        />
      </Card>

      {/* Detail Modal */}
      <Modal
        title="字段详情"
        open={showDetail}
        onCancel={() => setShowDetail(false)}
        footer={
          detailField && (
            <Space>
              <Button
                icon={<CheckOutlined />}
                type="primary"
                loading={submitLoading === detailField.id}
                onClick={() => handleSubmit(detailField.id)}
              >
                确认通过
              </Button>
              <Button
                icon={<EditOutlined />}
                onClick={() => {
                  form.setFieldsValue({
                    chinese_name: detailField.chinese_name || "",
                    business_definition: detailField.business_definition || "",
                    data_category: detailField.data_category,
                  });
                  setShowModify(true);
                }}
              >
                修改
              </Button>
              <Button
                danger
                icon={<CloseOutlined />}
                loading={submitLoading === detailField.id}
                onClick={() => handleReject(detailField.id)}
              >
                拒绝
              </Button>
            </Space>
          )
        }
      >
        {detailField && (
          <Space direction="vertical" style={{ width: "100%" }} size="middle">
            <Space>
              <Text strong>表：</Text>
              <Text>{detailField.table_name}</Text>
              <Text strong>列：</Text>
              <Text>{detailField.column_name}</Text>
              <Tag>{detailField.data_type}</Tag>
            </Space>
            <Divider />
            <Space style={{ width: "100%", justifyContent: "space-between" }}>
              <Text strong>中文名：</Text>
              <Text>{detailField.chinese_name || <Text type="secondary">未定义</Text>}</Text>
            </Space>
            <Space style={{ width: "100%", justifyContent: "space-between" }}>
              <Text strong>业务定义：</Text>
              <Text>{detailField.business_definition || <Text type="secondary">未定义</Text>}</Text>
            </Space>
            <Space style={{ width: "100%", justifyContent: "space-between" }}>
              <Text strong>取值规则：</Text>
              <Text>{detailField.value_rules || <Text type="secondary">未定义</Text>}</Text>
            </Space>
            <Space style={{ width: "100%", justifyContent: "space-between" }}>
              <Text strong>数据分类：</Text>
              <Tag color={categoryColor[detailField.data_category] || "default"}>
                {detailField.data_category}
              </Tag>
            </Space>
          </Space>
        )}
      </Modal>

      {/* Modify Modal */}
      <Modal
        title="修改字段语义"
        open={showModify}
        onOk={handleModifySubmit}
        onCancel={() => setShowModify(false)}
      >
        <Form form={form} layout="vertical">
          <Form.Item name="chinese_name" label="中文名">
            <Input placeholder="字段中文名" />
          </Form.Item>
          <Form.Item name="business_definition" label="业务定义">
            <Input.TextArea rows={3} placeholder="字段的业务含义" />
          </Form.Item>
          <Form.Item name="data_category" label="数据分类">
            <Select>
              <Select.Option value="dimension">维度</Select.Option>
              <Select.Option value="metric">指标</Select.Option>
              <Select.Option value="fact">事实</Select.Option>
              <Select.Option value="other">其他</Select.Option>
            </Select>
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
