import { Layout, Menu, Typography } from "antd";
import {
  DashboardOutlined,
  DatabaseOutlined,
  CheckSquareOutlined,
  UnorderedListOutlined,
  SearchOutlined,
} from "@ant-design/icons";
import { useNavigate, useLocation } from "react-router-dom";

const { Header, Sider, Content } = Layout;
const { Title } = Typography;

const menuItems = [
  { key: "/", icon: <DashboardOutlined />, label: "仪表盘" },
  { key: "/schema", icon: <DatabaseOutlined />, label: "Schema 浏览" },
  { key: "/review", icon: <CheckSquareOutlined />, label: "待审核队列" },
  { key: "/relationships", icon: <UnorderedListOutlined />, label: "表关系" },
  { key: "/query", icon: <SearchOutlined />, label: "自然语言查询" },
];

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const navigate = useNavigate();
  const location = useLocation();

  return (
    <Layout style={{ minHeight: "100vh" }}>
      <Sider
        breakpoint="lg"
        collapsedWidth="80"
        style={{ background: "#fff", borderRight: "1px solid #f0f0f0" }}
      >
        <div
          style={{
            padding: "16px 12px",
            textAlign: "center",
            borderBottom: "1px solid #f0f0f0",
          }}
        >
          <Title level={4} style={{ margin: 0, color: "#1677ff" }}>
            AI Scanner
          </Title>
        </div>
        <Menu
          mode="inline"
          selectedKeys={[location.pathname]}
          items={menuItems}
          onClick={({ key }) => navigate(key)}
          style={{ borderRight: "none" }}
        />
      </Sider>
      <Layout>
        <Header
          style={{
            background: "#fff",
            padding: "0 24px",
            borderBottom: "1px solid #f0f0f0",
            display: "flex",
            alignItems: "center",
          }}
        >
          <Title level={5} style={{ margin: 0 }}>
            AI 数据库语义层扫描工具
          </Title>
        </Header>
        <Content style={{ margin: 24, padding: 24, background: "#fff", borderRadius: 8 }}>
          {children}
        </Content>
      </Layout>
    </Layout>
  );
}
