import { useState, useEffect, useRef } from "react";
import {
  Tree,
  Card,
  Tag,
  Typography,
  Space,
  Button,
  message,
  Descriptions,
  Divider,
  Spin,
  Input,
  Select,
  Pagination,
} from "antd";
import {
  TableOutlined,
  FileOutlined,
  ReloadOutlined,
  EditOutlined,
  SaveOutlined,
  CloseOutlined,
} from "@ant-design/icons";
import {
  getDatabases,
  getTables,
  analyzeField,
  analyzeTable,
  getTableSemanticCache,
  getFieldSemanticCache,
  updateFieldSemantic,
  updateTableSemantic,
} from "../services/api";
import type {
  TableListResponse,
  TableSemanticResponse,
  FieldSemanticResponse,
  FieldSemanticCacheResponse,
  DataCategory,
} from "../types/api";

const { Text, Title } = Typography;
const { TextArea } = Input;

interface TreeNode {
  title: React.ReactNode;
  key: string;
  icon?: React.ReactNode;
  children?: TreeNode[];
  isLeaf?: boolean;
  db_name?: string;
  table_name?: string;
  column_name?: string;
}

export default function SchemaBrowser() {
  const [databases, setDatabases] = useState<string[]>([]);
  const [selectedDb, setSelectedDb] = useState<string>("");
  const [currentPage, setCurrentPage] = useState(1);
  const pageSize = 20;
  const [treeData, setTreeData] = useState<TreeNode[]>([]);
  const [selectedTable, setSelectedTable] = useState<string>("");
  const [selectedColumn, setSelectedColumn] = useState<string>("");
  const [columns, setColumns] = useState<TableListResponse["tables"][0]["columns"]>([]);
  const [tableComment, setTableComment] = useState<string>("");
  const [engine, setEngine] = useState<string>("");
  const [fieldSemantic, setFieldSemantic] = useState<FieldSemanticResponse | null>(null);
  const [fieldCache, setFieldCache] = useState<FieldSemanticCacheResponse | null>(null);
  const [tableFieldCache, setTableFieldCache] = useState<Map<string, FieldSemanticCacheResponse>>(new Map());
  const [tableSemantic, setTableSemantic] = useState<TableSemanticResponse | null>(null);
  const treeDataRef = useRef<TreeNode[]>([]);
  useEffect(() => {
    treeDataRef.current = treeData;
  }, [treeData]);
  const [isTableEditing, setIsTableEditing] = useState(false);
  const [tableEditForm, setTableEditForm] = useState<{
    chinese_name: string;
    business_definition: string;
    data_category: string;
  }>({ chinese_name: "", business_definition: "", data_category: "other" });
  const [loading, setLoading] = useState(false);
  const [dbLoading, setDbLoading] = useState(true);
  const [isEditing, setIsEditing] = useState(false);
  const [editForm, setEditForm] = useState<{
    chinese_name: string;
    business_definition: string;
    value_rules: string;
    data_category: string;
  }>({
    chinese_name: "",
    business_definition: "",
    value_rules: "",
    data_category: "other",
  });

  useEffect(() => {
    fetchDatabases();
  }, []);

  useEffect(() => {
    if (selectedDb) {
      setCurrentPage(1);
      setSelectedTable("");
      setSelectedColumn("");
      setTableSemantic(null);
      setTableFieldCache(new Map());
      setColumns([]);
      loadTables();
    }
  }, [selectedDb]);

  // Auto-scroll Tree to the page containing the selected table
  useEffect(() => {
    if (selectedTable && treeData.length > 0) {
      const idx = treeData.findIndex((t) => t.key === `table-${selectedTable}`);
      if (idx >= 0) {
        const targetPage = Math.floor(idx / pageSize) + 1;
        if (targetPage !== currentPage) {
          setCurrentPage(targetPage);
        }
      }
    }
  }, [selectedTable, treeData]);

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

  const loadTables = async () => {
    if (!selectedDb) return;
    setLoading(true);
    try {
      const res = await getTables(selectedDb);
      const data = res.data;
      const tree: TreeNode[] = [];
      for (const table of data.tables) {
        const treeNodes: TreeNode[] = table.columns.map((col) => ({
          title: (
            <span>
              {col.column_name}
              {col.is_primary_key && <Tag color="gold" style={{ marginLeft: 4 }}>PK</Tag>}
              <Tag color="default" style={{ marginLeft: 4 }}>{col.data_type}</Tag>
            </span>
          ),
          key: `col-${table.table_name}-${col.column_name}`,
          icon: <FileOutlined />,
          isLeaf: true,
          db_name: data.database,
          table_name: table.table_name,
          column_name: col.column_name,
        }));
        tree.push({
          title: (
            <span>
              {table.table_name}
              {table.table_comment && <Text type="secondary" style={{ marginLeft: 8, fontSize: 12 }}>{table.table_comment}</Text>}
            </span>
          ),
          key: `table-${table.table_name}`,
          icon: <TableOutlined />,
          children: treeNodes,
          db_name: data.database,
          table_name: table.table_name,
        });
      }
      setTreeData(tree);
    } catch {
      message.error("无法获取表列表");
    } finally {
      setLoading(false);
    }
  };

  // During render, just use current state without calling setState.
  // The useEffect above syncs currentPage when selectedTable changes.
  const effectivePage = currentPage;

  const paginatedTreeData = treeData.slice(
    (effectivePage - 1) * pageSize,
    effectivePage * pageSize
  );

  const handleSelect = async (_selectedKeys: React.Key[], info: { node: TreeNode }) => {
    const { node } = info;
    if (node.isLeaf && node.column_name) {
      setSelectedColumn(node.column_name);
      setSelectedTable(node.table_name!);
      setFieldSemantic(null);
      setFieldCache(null);
      setTableSemantic(null);
      setIsEditing(false);
      // Check preloaded cache first
      const preloaded = tableFieldCache.get(node.column_name);
      if (preloaded) {
        setFieldCache(preloaded);
        setFieldSemantic({
          id: preloaded.id,
          db_name: preloaded.db_name,
          table_name: preloaded.table_name,
          column_name: preloaded.column_name,
          data_type: preloaded.data_type,
          chinese_name: preloaded.chinese_name,
          business_definition: preloaded.business_definition,
          value_rules: preloaded.value_rules,
          related_fields: preloaded.related_fields,
          data_category: preloaded.data_category as FieldSemanticResponse["data_category"],
          status: (preloaded.status || "AUTO") as FieldSemanticResponse["status"],
        });
        setEditForm({
          chinese_name: preloaded.chinese_name || "",
          business_definition: preloaded.business_definition || "",
          value_rules: preloaded.value_rules || "",
          data_category: preloaded.data_category || "other",
        });
      } else {
        // Not preloaded, fetch individually
        try {
          const res = await getFieldSemanticCache(
            node.db_name!,
            node.table_name!,
            node.column_name
          );
          const cache = res.data;
          setFieldCache(cache);
          if (cache.has_semantics) {
            setFieldSemantic({
              id: cache.id,
              db_name: cache.db_name,
              table_name: cache.table_name,
              column_name: cache.column_name,
              data_type: cache.data_type,
              chinese_name: cache.chinese_name,
              business_definition: cache.business_definition,
              value_rules: cache.value_rules,
              related_fields: cache.related_fields,
              data_category: cache.data_category as FieldSemanticResponse["data_category"],
              status: (cache.status || "AUTO") as FieldSemanticResponse["status"],
            });
            setEditForm({
              chinese_name: cache.chinese_name || "",
              business_definition: cache.business_definition || "",
              value_rules: cache.value_rules || "",
              data_category: cache.data_category || "other",
            });
          }
        } catch {
          // Cache miss is expected for unanalyzed fields
        }
      }
    } else if (node.table_name) {
      // Clear stale table semantic data immediately
      setTableSemantic(null);
      // Calculate which page this table is on and jump there first,
      // so the Tree renders the correct page before selection is applied
      const tableIdx = treeData.findIndex((t) => t.key === `table-${node.table_name}`);
      if (tableIdx >= 0) {
        const targetPage = Math.floor(tableIdx / pageSize) + 1;
        if (targetPage !== currentPage) {
          setCurrentPage(targetPage);
        }
      }
      setSelectedTable(node.table_name);
      setSelectedColumn("");
      setFieldSemantic(null);
      setFieldCache(null);
      setIsEditing(false);
      // Find columns for this table
      const loadedColumns: TableListResponse["tables"][0]["columns"] = [];
      for (const t of treeData) {
        if (t.key === `table-${node.table_name}` && t.children) {
          const cols = t.children.map((c) => ({
            column_name: c.column_name!,
            table_name: node.table_name!,
            data_type: "",
            character_maximum_length: null,
            is_nullable: true,
            column_default: null,
            column_comment: "",
            is_primary_key: false,
            is_auto_increment: false,
            ordinal_position: 0,
          }));
          loadedColumns.push(...cols);
          break;
        }
      }
      setColumns(loadedColumns);
      setTableComment("");
      setEngine("");

      // Preload field & table semantics from ChromaDB (single API call)
      const newCache = new Map<string, FieldSemanticCacheResponse>();
      try {
        const res = await getTableSemanticCache(node.db_name!, node.table_name!);
        if (res.data.has_semantics) {
          // 填充字段缓存
          if (res.data.fields) {
            for (const f of res.data.fields) {
              const fieldId = `${node.db_name}.${node.table_name}.${f.column_name}`;
              newCache.set(f.column_name, {
                id: fieldId,
                db_name: f.db_name,
                table_name: f.table_name,
                column_name: f.column_name,
                data_type: f.data_type,
                chinese_name: f.chinese_name,
                business_definition: f.business_definition,
                value_rules: f.value_rules,
                related_fields: f.related_fields || [],
                data_category: f.data_category,
                status: f.status,
                has_semantics: true,
              });
            }
          }
          // 设置表级语义（从顶层字段读取）
          setTableSemantic({
            table_name: node.table_name!,
            db_name: node.db_name!,
            chinese_name: res.data.chinese_name || null,
            business_definition: res.data.business_definition || null,
            data_category: res.data.data_category as DataCategory,
            fields: res.data.fields || [],
          });
        }
      } catch {
        // Table cache miss - fields will be loaded on click
      }
      setTableFieldCache(newCache);
    }
  };

  const handleAnalyzeField = async () => {
    if (!selectedDb || !selectedTable || !selectedColumn) return;
    setLoading(true);
    try {
      const res = await analyzeField(selectedDb, selectedTable, selectedColumn);
      setFieldSemantic(res.data);
      setFieldCache(null);
      message.success("字段分析完成");
    } catch {
      message.error("字段分析失败");
    } finally {
      setLoading(false);
    }
  };

  const handleAnalyzeTable = async () => {
    if (!selectedDb || !selectedTable) return;
    setLoading(true);
    try {
      await analyzeTable(selectedDb, selectedTable);
      message.success("表分析完成");
      // Clear table cache and reload
      setTableFieldCache(new Map());
      await loadTables();
      // Re-select the table to refresh the detail view
      setSelectedColumn("");
      const node = treeDataRef.current.find((t) => t.key === `table-${selectedTable}`);
      if (node) {
        await handleSelect([`table-${selectedTable}`], { node });
      }
    } catch {
      message.error("表分析失败");
    } finally {
      setLoading(false);
    }
  };

  // Table-level edit functions
  const startTableEdit = () => {
    if (!tableSemantic) return;
    setTableEditForm({
      chinese_name: tableSemantic.chinese_name || "",
      business_definition: tableSemantic.business_definition || "",
      data_category: tableSemantic.data_category || "other",
    });
    setIsTableEditing(true);
  };

  const handleSaveTableEdit = async () => {
    if (!selectedDb || !selectedTable) return;
    setLoading(true);
    try {
      const changes: Record<string, unknown> = {};
      if (tableEditForm.chinese_name !== tableSemantic?.chinese_name) changes.chinese_name = tableEditForm.chinese_name || null;
      if (tableEditForm.business_definition !== tableSemantic?.business_definition) changes.business_definition = tableEditForm.business_definition || null;
      if (tableEditForm.data_category !== tableSemantic?.data_category) changes.data_category = tableEditForm.data_category;
      if (Object.keys(changes).length === 0) { setIsTableEditing(false); return; }
      await updateTableSemantic({ db_name: selectedDb, table_name: selectedTable, ...changes });
      // 刷新缓存
      const res = await getTableSemanticCache(selectedDb, selectedTable);
      if (res.data.has_semantics) {
        setTableSemantic({
          table_name: selectedTable, db_name: selectedDb,
          chinese_name: res.data.chinese_name || null,
          business_definition: res.data.business_definition || null,
          data_category: res.data.data_category as DataCategory,
          fields: res.data.fields || [],
        });
      }
      // 同步刷新 tableFieldCache
      const newCache = new Map<string, FieldSemanticCacheResponse>();
      if (res.data.fields) {
        for (const f of res.data.fields) {
          const fieldId = `${selectedDb}.${selectedTable}.${f.column_name}`;
          newCache.set(f.column_name, { ...f, id: fieldId });
        }
      }
      setTableFieldCache(newCache);
      setIsTableEditing(false);
      message.success("表语义保存成功");
    } catch {
      message.error("表语义保存失败");
    } finally {
      setLoading(false);
    }
  };

  const cancelTableEdit = () => setIsTableEditing(false);

  const startEdit = () => {
    if (!fieldSemantic) return;
    setEditForm({
      chinese_name: fieldSemantic.chinese_name || "",
      business_definition: fieldSemantic.business_definition || "",
      value_rules: fieldSemantic.value_rules || "",
      data_category: fieldSemantic.data_category || "other",
    });
    setIsEditing(true);
  };

  const handleSaveEdit = async () => {
    if (!selectedDb || !selectedTable || !selectedColumn) return;
    setLoading(true);
    try {
      const fieldId = `${selectedDb}.${selectedTable}.${selectedColumn}`;
      const updates: Record<string, unknown> = {};
      if (editForm.chinese_name !== fieldSemantic?.chinese_name) {
        updates.chinese_name = editForm.chinese_name || null;
      }
      if (editForm.business_definition !== fieldSemantic?.business_definition) {
        updates.business_definition = editForm.business_definition || null;
      }
      if (editForm.value_rules !== fieldSemantic?.value_rules) {
        updates.value_rules = editForm.value_rules || null;
      }
      if (editForm.data_category !== fieldSemantic?.data_category) {
        updates.data_category = editForm.data_category;
      }

      await updateFieldSemantic({ field_id: fieldId, ...updates });

      // Update local state
      const updated: FieldSemanticResponse = {
        ...fieldSemantic!,
        chinese_name: updates.chinese_name as string | null,
        business_definition: updates.business_definition as string | null,
        value_rules: updates.value_rules as string | null,
        data_category: updates.data_category as FieldSemanticResponse["data_category"],
      };
      setFieldSemantic(updated);
      setFieldCache(null);
      // Update table cache
      const updatedCache = new Map(tableFieldCache);
      updatedCache.set(selectedColumn!, {
        id: fieldId,
        db_name: selectedDb,
        table_name: selectedTable,
        column_name: selectedColumn!,
        data_type: updated.data_type,
        chinese_name: updated.chinese_name,
        business_definition: updated.business_definition,
        value_rules: updated.value_rules,
        related_fields: updated.related_fields,
        data_category: updated.data_category,
        status: updated.status,
        has_semantics: true,
      });
      setTableFieldCache(updatedCache);
      // Refresh table semantic cache too
      if (selectedDb && selectedTable) {
        try {
          const cacheRes = await getTableSemanticCache(selectedDb, selectedTable);
          if (cacheRes.data.has_semantics) {
            setTableSemantic({
              table_name: selectedTable, db_name: selectedDb,
              chinese_name: cacheRes.data.chinese_name || null,
              business_definition: cacheRes.data.business_definition || null,
              data_category: cacheRes.data.data_category as DataCategory,
              fields: cacheRes.data.fields || [],
            });
          }
        } catch { /* ignore */ }
      }
      setIsEditing(false);
      message.success("保存成功");
    } catch {
      message.error("保存失败");
    } finally {
      setLoading(false);
    }
  };

  const cancelEdit = () => {
    setIsEditing(false);
  };

  const categoryColor: Record<string, string> = {
    dimension: "purple",
    metric: "blue",
    fact: "green",
    other: "default",
  };

  const statusColor: Record<string, string> = {
    PENDING: "orange",
    CALIBRATED: "green",
    AUTO: "blue",
    SKIPPED: "default",
  };

  if (dbLoading) {
    return (
      <div style={{ textAlign: "center", padding: 48 }}>
        <Spin size="large" />
      </div>
    );
  }

  return (
    <div>
      <Title level={3}>Schema 浏览器</Title>
      <Space style={{ marginBottom: 16 }}>
        <select
          value={selectedDb}
          onChange={(e) => setSelectedDb(e.target.value)}
          style={{ padding: "4px 12px", borderRadius: 6, border: "1px solid #d9d9d9" }}
        >
          <option value="">-- 选择数据库 --</option>
          {databases.map((db) => (
            <option key={db} value={db}>{db}</option>
          ))}
        </select>
        <Button icon={<ReloadOutlined />} onClick={loadTables} disabled={!selectedDb}>
          刷新
        </Button>
        <Button onClick={handleAnalyzeTable} disabled={!selectedTable || loading}>
          分析整表
        </Button>
      </Space>

      <div style={{ display: "flex", gap: 16 }}>
        {/* Left: Tree */}
        <Card
          title="数据库结构"
          style={{ flex: 1, minWidth: 300 }}
          loading={loading}
        >
          <Tree
            treeData={paginatedTreeData}
            selectedKeys={selectedColumn ? [`col-${selectedTable}-${selectedColumn}`] : selectedTable ? [`table-${selectedTable}`] : []}
            onSelect={handleSelect}
            showLine
          />
          {treeData.length > pageSize && (
            <div style={{ marginTop: 12, textAlign: "center" }}>
              <Pagination
                current={currentPage}
                total={treeData.length}
                pageSize={pageSize}
                showSizeChanger={false}
                onChange={(page) => {
                  setCurrentPage(page);
                  setSelectedTable("");
                  setSelectedColumn("");
                }}
              />
            </div>
          )}
        </Card>

        {/* Right: Detail */}
        <Card
          title={
            selectedTable
              ? `${selectedTable}${tableComment ? ` (${tableComment})` : ""}`
              : "字段详情"
          }
          style={{ flex: 1 }}
        >
          {!selectedTable && <Text type="secondary">请在左侧选择表或字段</Text>}

          {selectedTable && !selectedColumn && (
            <div>
              {/* 表语义卡片 */}
              <div style={{ marginBottom: 16 }}>
                <Space style={{ marginBottom: 12 }} justify="space-between">
                  <Title level={4} style={{ margin: 0 }}>{selectedTable}</Title>
                  <Space>
                    <Button icon={<EditOutlined />} onClick={startTableEdit} disabled={loading}>编辑</Button>
                  </Space>
                </Space>
                {!isTableEditing ? (
                  <Descriptions bordered size="small" column={1}>
                    <Descriptions.Item label="中文名">
                      {tableSemantic?.chinese_name || <Text type="secondary">未定义</Text>}
                    </Descriptions.Item>
                    <Descriptions.Item label="业务定义">
                      {tableSemantic?.business_definition || <Text type="secondary">未定义</Text>}
                    </Descriptions.Item>
                    <Descriptions.Item label="数据分类">
                      {tableSemantic?.data_category ? (
                        <Tag color={categoryColor[tableSemantic.data_category]}>{tableSemantic.data_category}</Tag>
                      ) : <Text type="secondary">未定义</Text>}
                    </Descriptions.Item>
                  </Descriptions>
                ) : (
                  <div>
                    <div style={{ marginBottom: 8 }}>
                      <Text>中文名:</Text>
                      <TextArea value={tableEditForm.chinese_name}
                        onChange={(e) => setTableEditForm({...tableEditForm, chinese_name: e.target.value})}
                        style={{ marginTop: 4 }} rows={2} />
                    </div>
                    <div style={{ marginBottom: 8 }}>
                      <Text>业务定义:</Text>
                      <TextArea value={tableEditForm.business_definition}
                        onChange={(e) => setTableEditForm({...tableEditForm, business_definition: e.target.value})}
                        style={{ marginTop: 4 }} rows={3} />
                    </div>
                    <div style={{ marginBottom: 8 }}>
                      <Text>数据分类:</Text>
                      <Select value={tableEditForm.data_category}
                        onChange={(value) => setTableEditForm({...tableEditForm, data_category: value})}
                        style={{ width: "100%", marginTop: 4 }}>
                        <Select.Option value="dimension">维度 (dimension)</Select.Option>
                        <Select.Option value="metric">指标 (metric)</Select.Option>
                        <Select.Option value="fact">事实 (fact)</Select.Option>
                        <Select.Option value="other">其他 (other)</Select.Option>
                      </Select>
                    </div>
                    <Space>
                      <Button type="primary" icon={<SaveOutlined />} onClick={handleSaveTableEdit} disabled={loading}>保存</Button>
                      <Button icon={<CloseOutlined />} onClick={cancelTableEdit} disabled={loading}>取消</Button>
                    </Space>
                  </div>
                )}
              </div>

              <Divider plain style={{ margin: "12px 0" }}>字段列表 ({columns.length})</Divider>
              {columns.map((col) => {
                const cached = tableFieldCache.get(col.column_name);
                const hasAnalysis = cached?.has_semantics;
                return (
                  <div key={col.column_name} style={{ marginBottom: 8 }}>
                    <Space>
                      <Text strong>{col.column_name}</Text>
                      <Tag>{col.data_type}</Tag>
                      {col.is_primary_key && <Tag color="gold">PK</Tag>}
                      {col.is_auto_increment && <Tag color="cyan">Auto</Tag>}
                      {col.is_nullable ? <Tag>Nullable</Tag> : <Tag color="red">NOT NULL</Tag>}
                      {hasAnalysis && (
                        <Tag color="green">已分析</Tag>
                      )}
                      {!hasAnalysis && (
                        <Tag color="default">未分析</Tag>
                      )}
                    </Space>
                  </div>
                );
              })}
            </div>
          )}

          {selectedColumn && (
            <div>
              {!fieldCache?.has_semantics && !fieldSemantic && (
                <div style={{ marginBottom: 16 }}>
                  <Tag color="orange">未分析</Tag>
                  <Space style={{ marginLeft: 8 }}>
                    <Button type="primary" onClick={handleAnalyzeField} disabled={loading}>
                      分析字段语义
                    </Button>
                  </Space>
                </div>
              )}

              {loading && !fieldSemantic && <Spin />}

              {fieldSemantic && !isEditing && (
                <div>
                  <Space style={{ marginBottom: 16 }}>
                    {fieldCache?.has_semantics && (
                      <Tag color="green">已分析</Tag>
                    )}
                    <Button icon={<EditOutlined />} onClick={startEdit}>
                      编辑
                    </Button>
                  </Space>

                  <Descriptions bordered size="small" column={1}>
                    <Descriptions.Item label="中文名">
                      {fieldSemantic.chinese_name || <Text type="secondary">未定义</Text>}
                    </Descriptions.Item>
                    <Descriptions.Item label="业务定义">
                      {fieldSemantic.business_definition || <Text type="secondary">未定义</Text>}
                    </Descriptions.Item>
                    <Descriptions.Item label="取值规则">
                      {fieldSemantic.value_rules || <Text type="secondary">未定义</Text>}
                    </Descriptions.Item>
                    <Descriptions.Item label="数据分类">
                      <Tag color={categoryColor[fieldSemantic.data_category] || "default"}>
                        {fieldSemantic.data_category}
                      </Tag>
                    </Descriptions.Item>
                    <Descriptions.Item label="状态">
                      <Tag color={statusColor[fieldSemantic.status] || "default"}>
                        {fieldSemantic.status}
                      </Tag>
                    </Descriptions.Item>
                    {fieldSemantic.related_fields.length > 0 && (
                      <Descriptions.Item label="关联字段">
                        {fieldSemantic.related_fields.map((f) => (
                          <Tag key={f}>{f}</Tag>
                        ))}
                      </Descriptions.Item>
                    )}
                  </Descriptions>
                </div>
              )}

              {fieldSemantic && isEditing && (
                <div>
                  <div style={{ marginBottom: 12 }}>
                    <div style={{ marginBottom: 8 }}>
                      <Text>中文名:</Text>
                      <TextArea
                        value={editForm.chinese_name}
                        onChange={(e) =>
                          setEditForm({ ...editForm, chinese_name: e.target.value })
                        }
                        style={{ marginTop: 4 }}
                        rows={2}
                      />
                    </div>
                    <div style={{ marginBottom: 8 }}>
                      <Text>业务定义:</Text>
                      <TextArea
                        value={editForm.business_definition}
                        onChange={(e) =>
                          setEditForm({ ...editForm, business_definition: e.target.value })
                        }
                        style={{ marginTop: 4 }}
                        rows={3}
                      />
                    </div>
                    <div style={{ marginBottom: 8 }}>
                      <Text>取值规则:</Text>
                      <TextArea
                        value={editForm.value_rules}
                        onChange={(e) =>
                          setEditForm({ ...editForm, value_rules: e.target.value })
                        }
                        style={{ marginTop: 4 }}
                        rows={2}
                      />
                    </div>
                    <div style={{ marginBottom: 8 }}>
                      <Text>数据分类:</Text>
                      <Select
                        value={editForm.data_category}
                        onChange={(value) =>
                          setEditForm({ ...editForm, data_category: value })
                        }
                        style={{ width: "100%", marginTop: 4 }}
                      >
                        <Select.Option value="dimension">维度 (dimension)</Select.Option>
                        <Select.Option value="metric">指标 (metric)</Select.Option>
                        <Select.Option value="fact">事实 (fact)</Select.Option>
                        <Select.Option value="other">其他 (other)</Select.Option>
                      </Select>
                    </div>
                  </div>
                  <Space>
                    <Button type="primary" icon={<SaveOutlined />} onClick={handleSaveEdit} disabled={loading}>
                      保存
                    </Button>
                    <Button icon={<CloseOutlined />} onClick={cancelEdit} disabled={loading}>
                      取消
                    </Button>
                  </Space>
                </div>
              )}
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
