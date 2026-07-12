# mobaobubao
This is a tool designed to assist with calligraphy writing and creation.

src/
├── types/index.ts          # 所有类型定义（Glyph, Copybook, Composition...）
├── store/
│   └── compositionStore.ts # Zustand 全局状态
├── lib/
│   ├── grid.ts             # 米字格/九宫格 SVG 路径生成
│   └── mockData.ts         # 占位字形数据（之后换成真实 API）
├── hooks/
│   └── useResizablePanel.ts # 拖拽分割线逻辑
├── components/
│   ├── ui/
│   │   ├── CharCell.tsx    # 单个字格
│   │   ├── PaperGrid.tsx   # 竖排从右到左网格
│   │   └── PreviewPanel.tsx # 右侧大字预览 + 字形选择
│   └── layout/
│       └── Toolbar.tsx     # 顶部工具栏
└── pages/
    └── ComposePage.tsx     # 主页面（含拖拽分割）
    
# 墨迹 API

FastAPI + Prisma + PostgreSQL backend.

## 本地启动

```bash
# 1. 复制环境变量
cp .env.example .env
# 编辑 .env，填入 PostgreSQL 连接串

# 2. 安装依赖
pip install -e ".[dev]"

# 3. 生成 Prisma client + 建表
prisma generate
prisma db push          # 开发用；生产用 prisma migrate deploy

# 4. 启动
uvicorn app.main:app --reload --port 8000
```

## API 文档

启动后访问 http://localhost:8000/docs

## 主要接口

| Method | Path | 说明 |
|--------|------|------|
| POST | /api/copybooks | 新建字帖 |
| GET  | /api/copybooks | 列出所有字帖 |
| POST | /api/copybooks/{id}/pages | 上传页面图片（自动触发切割）|
| GET  | /api/copybooks/{id}/pages | 查看字帖页码列表 |
| GET  | /api/glyphs?character=月 | 查询某字的所有字形 |
| PATCH| /api/glyphs/{id}/label | 人工标注字形 |
| GET  | /api/glyphs/unverified | 待审核字形列表 |

## 上传流程

```
POST /api/copybooks          → 拿到 copybook_id
POST /api/copybooks/{id}/pages  (multipart: file + page_number)
  → 后台自动运行 OpenCV 分割
  → 每个检测到的字存入 Glyph 表，character="?"
POST /api/glyphs/{id}/label  → 人工/OCR 填写真实汉字
```