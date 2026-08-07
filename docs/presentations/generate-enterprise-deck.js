/**
 * AINews 企业客户演示 PPT v1
 * Run: node generate-enterprise-deck.js
 */
const pptxgen = require("pptxgenjs");
const React = require("react");
const ReactDOMServer = require("react-dom/server");
const sharp = require("sharp");
const path = require("path");
const {
  MdFolderOpen,
  MdTimeline,
  MdDevices,
  MdAccessTime,
  MdCloudUpload,
  MdLink,
  MdEditNote,
  MdAutoAwesome,
  MdGavel,
  MdHub,
  MdStarRate,
  MdImage,
  MdMovie,
  MdMic,
  MdPublish,
  MdSecurity,
  MdWeb,
  MdDashboard,
  MdRocketLaunch,
  MdSpeed,
  MdSavings,
  MdShield,
  MdExtension,
  MdHandshake,
} = require("react-icons/md");

const OUT = path.join(__dirname, "智能内容生产平台-企业客户演示-v1.pptx");

// Graphite Luxe — obsidian, champagne gold, warm stone
const C = {
  navy: "141416", // ink — primary dark
  graphite: "2A2A2E", // layered dark surfaces
  ice: "E8E4DE", // mist — text & lines on dark
  white: "FAF9F7", // pearl
  teal: "B8956B", // champagne — primary accent
  mint: "D4B896", // soft gold — highlights
  bronze: "96785A", // deep gold — emphasis
  light: "F7F5F2", // stone — light page background
  slate: "6E6A65", // muted body text
  dark: "1C1C1E", // primary text on light
  card: "F0ECE6", // warm card fill
  border: "E0DBD4", // subtle dividers
  burgundy: "9E4B4B", // refined alert
};

async function iconData(Icon, color = C.white, size = 256) {
  const svg = ReactDOMServer.renderToStaticMarkup(
    React.createElement(Icon, { color: `#${color}`, size: String(size) })
  );
  const buf = await sharp(Buffer.from(svg)).resize(size, size).png().toBuffer();
  return `image/png;base64,${buf.toString("base64")}`;
}

function shadow() {
  return { type: "outer", color: "000000", blur: 4, offset: 2, angle: 135, opacity: 0.15 };
}

function addFooter(slide, page, total = 18, color = C.slate) {
  slide.addText(`${page} / ${total}`, {
    x: 9.1,
    y: 5.25,
    w: 0.8,
    h: 0.25,
    fontSize: 9,
    color,
    align: "right",
    margin: 0,
  });
}

function addTitle(slide, text, opts = {}) {
  slide.addText(text, {
    x: 0.5,
    y: 0.35,
    w: 9,
    h: 0.7,
    fontFace: "Cambria",
    fontSize: opts.size || 32,
    bold: true,
    color: opts.color || C.navy,
    margin: 0,
  });
}

function addDarkBg(slide) {
  slide.background = { color: C.navy };
}

function addLightBg(slide) {
  slide.background = { color: C.white };
}

function addCard(slide, { x, y, w, h, fill = C.light }) {
  slide.addShape("roundRect", {
    x,
    y,
    w,
    h,
    fill: { color: fill },
    line: { color: C.border, width: 0.5 },
    rectRadius: 0.08,
    shadow: shadow(),
  });
}

function addIconBadge(slide, data, x, y, bg = C.navy) {
  slide.addShape("ellipse", {
    x,
    y,
    w: 0.55,
    h: 0.55,
    fill: { color: bg },
    line: { color: bg, width: 0 },
  });
  slide.addImage({ data, x: x + 0.1, y: y + 0.1, w: 0.35, h: 0.35 });
}

function bulletItems(items, color = C.dark, size = 14) {
  return items.map((text, i) => ({
    text,
    options: {
      bullet: true,
      breakLine: i < items.length - 1,
      fontSize: size,
      color,
      fontFace: "Calibri",
      paraSpaceAfter: 6,
    },
  }));
}

async function main() {
  const icons = {
    folder: await iconData(MdFolderOpen),
    timeline: await iconData(MdTimeline),
    devices: await iconData(MdDevices),
    time: await iconData(MdAccessTime),
    upload: await iconData(MdCloudUpload),
    link: await iconData(MdLink),
    edit: await iconData(MdEditNote),
    ai: await iconData(MdAutoAwesome),
    gavel: await iconData(MdGavel),
    hub: await iconData(MdHub),
    star: await iconData(MdStarRate),
    image: await iconData(MdImage),
    movie: await iconData(MdMovie),
    mic: await iconData(MdMic),
    publish: await iconData(MdPublish),
    security: await iconData(MdSecurity),
    web: await iconData(MdWeb),
    dashboard: await iconData(MdDashboard),
    rocket: await iconData(MdRocketLaunch),
    speed: await iconData(MdSpeed),
    savings: await iconData(MdSavings),
    shield: await iconData(MdShield),
    extension: await iconData(MdExtension),
    handshake: await iconData(MdHandshake),
  };

  const pres = new pptxgen();
  pres.layout = "LAYOUT_16x9";
  pres.author = "AINews";
  pres.title = "智能内容生产平台 - 企业客户演示";

  // ── Slide 1: Cover ──────────────────────────────────────────
  {
    const slide = pres.addSlide();
    addDarkBg(slide);
    slide.addShape("roundRect", {
      x: 6.2,
      y: 0.6,
      w: 3.3,
      h: 4.4,
      fill: { color: C.graphite, transparency: 15 },
      line: { color: C.teal, width: 0.75 },
      rectRadius: 0.1,
    });
    slide.addShape("roundRect", {
      x: 6.5,
      y: 0.9,
      w: 2.2,
      h: 3.8,
      fill: { color: C.navy, transparency: 20 },
      line: { color: C.mint, width: 0.5 },
      rectRadius: 0.12,
    });
    slide.addText("9:16", {
      x: 7.0,
      y: 2.5,
      w: 1.2,
      h: 0.4,
      fontSize: 14,
      color: C.mint,
      align: "center",
      margin: 0,
    });
    slide.addText("智能内容生产平台", {
      x: 0.6,
      y: 1.5,
      w: 5.5,
      h: 1.0,
      fontFace: "Cambria",
      fontSize: 40,
      bold: true,
      color: C.white,
      margin: 0,
    });
    slide.addText("多源资讯与素材 · 一键生成短视频 · 多平台发布", {
      x: 0.6,
      y: 2.55,
      w: 5.4,
      h: 0.6,
      fontSize: 18,
      color: C.ice,
      margin: 0,
    });
    slide.addText("企业级 · 可私有化部署 · 浏览器即用", {
      x: 0.6,
      y: 3.35,
      w: 5.0,
      h: 0.4,
      fontSize: 14,
      color: C.teal,
      margin: 0,
    });
    slide.addText("AINews · 2026", {
      x: 0.6,
      y: 4.85,
      w: 3.0,
      h: 0.3,
      fontSize: 11,
      color: C.ice,
      margin: 0,
    });
    slide.addNotes(
      "各位好。今天介绍的是一套面向企业的智能内容生产平台。它不绑定某一类资讯，行业新闻、官网内容、内部素材、活动稿件都可以接入，统一加工成适合短视频平台发布的成片。"
    );
  }

  // ── Slide 2: Challenges ─────────────────────────────────────
  {
    const slide = pres.addSlide();
    addLightBg(slide);
    addTitle(slide, "企业内容团队的现实挑战");
    const pains = [
      { icon: icons.folder, title: "来源分散", desc: "官网、媒体、内部文档、活动素材各自为政" },
      { icon: icons.timeline, title: "链路冗长", desc: "选题→写稿→配图→剪辑→配音→审核→发布" },
      { icon: icons.devices, title: "平台各异", desc: "标题、标签、时长、合规规则不统一" },
      { icon: icons.time, title: "产能不足", desc: "人力成本高，产出节奏跟不上业务需求" },
    ];
    pains.forEach((p, i) => {
      const col = i % 2;
      const row = Math.floor(i / 2);
      const x = 0.55 + col * 4.7;
      const y = 1.25 + row * 2.05;
      addCard(slide, { x, y, w: 4.35, h: 1.75 });
      addIconBadge(slide, p.icon, x + 0.2, y + 0.25, C.navy);
      slide.addText(p.title, {
        x: x + 0.9,
        y: y + 0.22,
        w: 3.2,
        h: 0.35,
        fontSize: 18,
        bold: true,
        color: C.navy,
        margin: 0,
      });
      slide.addText(p.desc, {
        x: x + 0.9,
        y: y + 0.65,
        w: 3.1,
        h: 0.8,
        fontSize: 13,
        color: C.slate,
        margin: 0,
      });
    });
    slide.addText("团队很忙，但内容产出跟不上", {
      x: 0.55,
      y: 5.0,
      w: 9,
      h: 0.35,
      fontSize: 16,
      italic: true,
      bold: true,
      color: C.teal,
      align: "center",
      margin: 0,
    });
    addFooter(slide, 2);
    slide.addNotes("很多企业的内容团队并不是缺素材，而是缺效率。采购这类系统，本质上是在买产能、一致性和风控能力。");
  }

  // ── Slide 3: Solution ───────────────────────────────────────
  {
    const slide = pres.addSlide();
    addLightBg(slide);
    addTitle(slide, "一套系统，打通内容生产全链路");
    const keys = ["接入灵活", "加工智能", "成片快速", "发布可控"];
    keys.forEach((k, i) => {
      const x = 0.55 + i * 2.35;
      addCard(slide, { x, y: 1.2, w: 2.15, h: 1.5, fill: C.navy });
      slide.addText(k, {
        x,
        y: 1.75,
        w: 2.15,
        h: 0.5,
        fontSize: 16,
        bold: true,
        color: C.white,
        align: "center",
        margin: 0,
      });
      if (i < 3) {
        slide.addShape("rightArrow", {
          x: x + 2.2,
          y: 1.85,
          w: 0.12,
          h: 0.2,
          fill: { color: C.teal },
          line: { color: C.teal, width: 0 },
        });
      }
    });
    slide.addText(
      bulletItems([
        "不限资讯类型，任意图文素材均可接入",
        "重复环节自动化，关键节点保留人工审核",
        "本地部署，数据与账号企业自主掌控",
      ]),
      { x: 0.7, y: 3.0, w: 8.6, h: 1.8, margin: 0 }
    );
    addCard(slide, { x: 0.55, y: 4.35, w: 4.2, h: 0.95, fill: C.card });
    addCard(slide, { x: 5.0, y: 4.35, w: 4.45, h: 0.95, fill: C.graphite });
    slide.addText("传统：多工具 + 多角色", {
      x: 0.7,
      y: 4.55,
      w: 3.8,
      h: 0.5,
      fontSize: 13,
      color: C.slate,
      margin: 0,
    });
    slide.addText("本平台：一条链路完成", {
      x: 5.15,
      y: 4.55,
      w: 4.1,
      h: 0.5,
      fontSize: 14,
      bold: true,
      color: C.mint,
      margin: 0,
    });
    addFooter(slide, 3);
    slide.addNotes("把内容生产从项目制变成流水线。对企业采购来说，价值是缩短制作周期、降低人力依赖、提升发布效率、控制合规风险。");
  }

  // ── Slide 4: Positioning ────────────────────────────────────
  {
    const slide = pres.addSlide();
    addLightBg(slide);
    addTitle(slide, "面向企业的内容生产与分发平台");
    const teams = ["品牌市场部", "新媒体运营", "政企宣传", "行业资讯运营", "产品营销团队"];
    teams.forEach((t, i) => {
      const angle = (i / teams.length) * 2 * Math.PI - Math.PI / 2;
      const cx = 7.0 + Math.cos(angle) * 1.6;
      const cy = 2.85 + Math.sin(angle) * 1.35;
      slide.addShape("ellipse", {
        x: cx - 0.55,
        y: cy - 0.3,
        w: 1.1,
        h: 0.6,
        fill: { color: C.card },
        line: { color: C.teal, width: 0.75 },
      });
      slide.addText(t, {
        x: cx - 0.55,
        y: cy - 0.18,
        w: 1.1,
        h: 0.36,
        fontSize: 9,
        color: C.navy,
        align: "center",
        margin: 0,
      });
    });
    addCard(slide, { x: 0.55, y: 1.15, w: 4.8, h: 3.5 });
    slide.addText("平台界面", {
      x: 0.75,
      y: 1.35,
      w: 4.4,
      h: 0.35,
      fontSize: 14,
      bold: true,
      color: C.navy,
      margin: 0,
    });
    slide.addShape("rect", {
      x: 0.85,
      y: 1.85,
      w: 4.2,
      h: 0.35,
      fill: { color: C.navy },
      line: { color: C.navy, width: 0 },
    });
    ["内容快做", "内容库", "发布中心", "设置"].forEach((tab, i) => {
      slide.addText(tab, {
        x: 0.95 + i * 1.0,
        y: 1.9,
        w: 0.9,
        h: 0.25,
        fontSize: 8,
        color: C.white,
        margin: 0,
      });
    });
    slide.addShape("rect", {
      x: 0.85,
      y: 2.3,
      w: 4.2,
      h: 2.1,
      fill: { color: C.white },
      line: { color: C.border, width: 0.5 },
    });
    slide.addText("可配置 · 可审核 · 可扩展", {
      x: 0.55,
      y: 4.85,
      w: 9,
      h: 0.35,
      fontSize: 18,
      bold: true,
      color: C.teal,
      align: "center",
      margin: 0,
    });
    addFooter(slide, 4);
    slide.addNotes("这不是单点工具，而是可配置的内容生产平台。采购方重点看：能不能接你们的源、能不能控你们的流程、能不能扩你们的平台。");
  }

  // ── Slide 5: Flow ───────────────────────────────────────────
  {
    const slide = pres.addSlide();
    addLightBg(slide);
    addTitle(slide, "从素材到发布，一条链路完成");
    const steps = ["多源接入", "统一入库", "智能选题", "文案生成", "素材匹配", "视频合成", "合规校验", "多平台发布"];
    const startX = 0.35;
    const stepW = 1.12;
    steps.forEach((s, i) => {
      const x = startX + i * 1.18;
      slide.addShape("roundRect", {
        x,
        y: 1.35,
        w: stepW,
        h: 0.75,
        fill: { color: i % 2 === 0 ? C.navy : C.bronze },
        line: { color: i % 2 === 0 ? C.navy : C.bronze, width: 0 },
        rectRadius: 0.06,
      });
      slide.addText(s, {
        x,
        y: 1.55,
        w: stepW,
        h: 0.4,
        fontSize: 9,
        bold: true,
        color: C.white,
        align: "center",
        margin: 0,
      });
      if (i < steps.length - 1) {
        slide.addShape("rightArrow", {
          x: x + stepW + 0.01,
          y: 1.62,
          w: 0.05,
          h: 0.18,
          fill: { color: C.slate },
          line: { color: C.slate, width: 0 },
        });
      }
    });
    const entries = [
      { label: "单条快做", color: C.mint },
      { label: "批量选题", color: C.teal },
      { label: "排期发布", color: C.navy },
    ];
    entries.forEach((e, i) => {
      addCard(slide, { x: 0.55 + i * 3.1, y: 2.55, w: 2.85, h: 1.0, fill: C.light });
      slide.addText(e.label, {
        x: 0.55 + i * 3.1,
        y: 2.85,
        w: 2.85,
        h: 0.4,
        fontSize: 16,
        bold: true,
        color: e.color,
        align: "center",
        margin: 0,
      });
    });
    slide.addText("三个入口，覆盖不同业务节奏", {
      x: 0.55,
      y: 3.75,
      w: 9,
      h: 0.35,
      fontSize: 14,
      color: C.slate,
      align: "center",
      margin: 0,
    });
    addCard(slide, { x: 0.55, y: 4.2, w: 8.9, h: 0.85, fill: C.card });
    slide.addText("把分散的工具和人工协作，收敛成一套标准流程", {
      x: 0.75,
      y: 4.45,
      w: 8.5,
      h: 0.4,
      fontSize: 15,
      bold: true,
      color: C.navy,
      align: "center",
      margin: 0,
    });
    addFooter(slide, 5);
    slide.addNotes("左边是输入：不限来源。中间是加工：系统完成重复劳动，人在关键节点确认。右边是输出：按平台规则校验后分发。");
  }

  // ── Slide 6: Ingestion ──────────────────────────────────────
  {
    const slide = pres.addSlide();
    addLightBg(slide);
    addTitle(slide, "任何资讯、任何素材，都能接入");
    const modes = [
      { icon: icons.upload, title: "定时采集", desc: "按企业需求配置多个资讯源，自动入库" },
      { icon: icons.link, title: "链接导入", desc: "粘贴任意 URL，快速处理单条内容" },
      { icon: icons.edit, title: "手动录入", desc: "直接粘贴正文或上传图文素材" },
    ];
    modes.forEach((m, i) => {
      const y = 1.2 + i * 1.35;
      addCard(slide, { x: 0.55, y, w: 4.3, h: 1.15 });
      addIconBadge(slide, m.icon, 0.75, y + 0.3, C.navy);
      slide.addText(m.title, {
        x: 1.45,
        y: y + 0.22,
        w: 3.2,
        h: 0.35,
        fontSize: 17,
        bold: true,
        color: C.navy,
        margin: 0,
      });
      slide.addText(m.desc, {
        x: 1.45,
        y: y + 0.58,
        w: 3.1,
        h: 0.45,
        fontSize: 12,
        color: C.slate,
        margin: 0,
      });
    });
    addCard(slide, { x: 5.2, y: 1.2, w: 4.25, h: 3.95 });
    slide.addText("内容库示意", {
      x: 5.4,
      y: 1.35,
      w: 3.8,
      h: 0.3,
      fontSize: 13,
      bold: true,
      color: C.navy,
      margin: 0,
    });
    ["行业媒体资讯", "企业官网文章", "活动通稿", "内部资料文档"].forEach((row, i) => {
      slide.addShape("rect", {
        x: 5.45,
        y: 1.85 + i * 0.75,
        w: 3.75,
        h: 0.55,
        fill: { color: C.white },
        line: { color: C.border, width: 0.5 },
      });
      slide.addText(row, {
        x: 5.6,
        y: 1.98 + i * 0.75,
        w: 3.4,
        h: 0.3,
        fontSize: 11,
        color: C.dark,
        margin: 0,
      });
    });
    slide.addText("多源同题合并 · 新增来源可配置扩展", {
      x: 0.55,
      y: 5.0,
      w: 9,
      h: 0.3,
      fontSize: 13,
      italic: true,
      color: C.teal,
      margin: 0,
    });
    addFooter(slide, 6);
    slide.addNotes("接入足够灵活。不绑死某几家媒体，也不绑死某一种内容形态。新增来源主要通过配置扩展。");
  }

  // ── Slide 7: Content Engine ───────────────────────────────────
  {
    const slide = pres.addSlide();
    addLightBg(slide);
    addTitle(slide, "自动生成，人工确认");
    addCard(slide, { x: 0.55, y: 1.15, w: 4.0, h: 3.6, fill: C.card });
    slide.addText("输入：原文内容", {
      x: 0.75,
      y: 1.3,
      w: 3.6,
      h: 0.3,
      fontSize: 13,
      bold: true,
      color: C.navy,
      margin: 0,
    });
    slide.addText("……文章正文与配图……", {
      x: 0.85,
      y: 1.75,
      w: 3.4,
      h: 2.5,
      fontSize: 11,
      color: C.slate,
      margin: 0,
    });
    slide.addShape("rightArrow", {
      x: 4.65,
      y: 2.7,
      w: 0.5,
      h: 0.35,
      fill: { color: C.bronze },
      line: { color: C.bronze, width: 0 },
    });
    slide.addText("一键生成", {
      x: 4.55,
      y: 3.1,
      w: 0.7,
      h: 0.25,
      fontSize: 9,
      color: C.teal,
      align: "center",
      margin: 0,
    });
    addCard(slide, { x: 5.3, y: 1.15, w: 4.15, h: 3.6 });
    slide.addText("输出", {
      x: 5.5,
      y: 1.3,
      w: 3.8,
      h: 0.3,
      fontSize: 13,
      bold: true,
      color: C.navy,
      margin: 0,
    });
    slide.addText(
      bulletItems(
        ["标题 · 摘要 · 口播稿 · 话题标签", "按平台特性优化文案结构", "内置合规检测，敏感表述自动拦截", "支持多家大模型，可按场景切换"],
        C.dark,
        12
      ),
      { x: 5.45, y: 1.7, w: 3.85, h: 2.8, margin: 0 }
    );
    addIconBadge(slide, icons.ai, 8.55, 4.55, C.bronze);
    addFooter(slide, 7);
    slide.addNotes("智能加工而不是简单摘要。运营不需要从零写稿，在系统版本上审核修改确认。模型不绑定单一供应商。");
  }

  // ── Slide 8: Selection ────────────────────────────────────────
  {
    const slide = pres.addSlide();
    addLightBg(slide);
    addTitle(slide, "帮团队做选题和配图决策");
    const feats = [
      { icon: icons.star, title: "内容评分", desc: "自动评估优先级，推荐高价值选题" },
      { icon: icons.image, title: "智能配图", desc: "评估图片相关性，自动挑选最佳素材" },
      { icon: icons.edit, title: "素材处理", desc: "封面生成 · 去水印 · 裁剪替换" },
    ];
    feats.forEach((f, i) => {
      const y = 1.15 + i * 1.35;
      addCard(slide, { x: 0.55, y, w: 4.5, h: 1.15 });
      addIconBadge(slide, f.icon, 0.75, y + 0.3, C.navy);
      slide.addText(f.title, {
        x: 1.45,
        y: y + 0.2,
        w: 3.5,
        h: 0.35,
        fontSize: 16,
        bold: true,
        color: C.navy,
        margin: 0,
      });
      slide.addText(f.desc, {
        x: 1.45,
        y: y + 0.58,
        w: 3.4,
        h: 0.45,
        fontSize: 12,
        color: C.slate,
        margin: 0,
      });
    });
    addCard(slide, { x: 5.35, y: 1.15, w: 4.1, h: 3.95 });
    ["S 级选题", "A 级选题", "B 级选题"].forEach((g, i) => {
      const badgeY = 1.4 + i * 0.55;
      const badgeColor = i === 0 ? C.teal : i === 1 ? C.navy : C.slate;
      slide.addShape("roundRect", {
        x: 5.55,
        y: badgeY,
        w: 1.2,
        h: 0.3,
        fill: { color: badgeColor },
        line: { color: badgeColor, width: 0 },
        rectRadius: 0.05,
      });
      slide.addText(g, {
        x: 5.55,
        y: badgeY + 0.02,
        w: 1.2,
        h: 0.28,
        fontSize: 10,
        bold: true,
        color: C.white,
        align: "center",
        margin: 0,
      });
    });
    [0, 1, 2].forEach((i) => {
      slide.addShape("rect", {
        x: 6.9 + i * 0.75,
        y: 3.0,
        w: 0.65,
        h: 1.0,
        fill: { color: C.card },
        line: { color: i === 1 ? C.teal : C.border, width: i === 1 ? 2 : 0.5 },
      });
    });
    slide.addText("80% 重复判断自动化，专业人员聚焦创意", {
      x: 0.55,
      y: 5.0,
      w: 9,
      h: 0.3,
      fontSize: 14,
      bold: true,
      color: C.teal,
      align: "center",
      margin: 0,
    });
    addFooter(slide, 8);
    slide.addNotes("帮团队做选题和配图决策。把80%的重复判断自动化，让专业人员把时间花在真正需要创意的20%上。");
  }

  // ── Slide 9: Video ────────────────────────────────────────────
  {
    const slide = pres.addSlide();
    addLightBg(slide);
    addTitle(slide, "图文内容，稳定转成可发布视频");
    slide.addShape("roundRect", {
      x: 0.55,
      y: 1.15,
      w: 2.4,
      h: 3.8,
      fill: { color: C.navy },
      line: { color: C.ice, width: 1 },
      rectRadius: 0.1,
    });
    slide.addText("竖屏 9:16", {
      x: 0.55,
      y: 1.35,
      w: 2.4,
      h: 0.3,
      fontSize: 11,
      color: C.ice,
      align: "center",
      margin: 0,
    });
    slide.addText("标题示例", {
      x: 0.7,
      y: 2.2,
      w: 2.1,
      h: 0.5,
      fontSize: 12,
      bold: true,
      color: C.white,
      align: "center",
      margin: 0,
    });
    slide.addShape("rect", {
      x: 0.85,
      y: 2.85,
      w: 1.8,
      h: 1.2,
      fill: { color: C.bronze },
      line: { color: C.bronze, width: 0 },
    });
    slide.addText("滚动字幕", {
      x: 0.7,
      y: 4.35,
      w: 2.1,
      h: 0.3,
      fontSize: 9,
      color: C.mint,
      align: "center",
      margin: 0,
    });
    slide.addText(
      bulletItems(
        ["标准竖屏 1080×1920", "关键帧 · 字幕 · 配乐 · 配音", "TTS 语音与声音克隆", "数字人 · 画中画 · 品牌模板"],
        C.dark,
        13
      ),
      { x: 3.2, y: 1.25, w: 3.5, h: 2.5, margin: 0 }
    );
    const ext = [
      { icon: icons.movie, label: "视频合成" },
      { icon: icons.mic, label: "配音旁白" },
      { icon: icons.image, label: "品牌模板" },
    ];
    ext.forEach((e, i) => {
      addIconBadge(slide, e.icon, 6.95, 1.25 + i * 1.15, C.navy);
      slide.addText(e.label, {
        x: 7.65,
        y: 1.4 + i * 1.15,
        w: 2.0,
        h: 0.35,
        fontSize: 13,
        color: C.navy,
        margin: 0,
      });
    });
    addFooter(slide, 9);
    slide.addNotes("具备视频生产的技术深度，但使用门槛足够低。不是买一个会剪视频的工具，而是买一套能规模化出片的生产能力。");
  }

  // ── Slide 10: Publishing ──────────────────────────────────────
  {
    const slide = pres.addSlide();
    addLightBg(slide);
    addTitle(slide, "生成之后，直接发布");
    addCard(slide, { x: 0.55, y: 1.15, w: 5.0, h: 3.7 });
    slide.addText("发布中心", {
      x: 0.75,
      y: 1.3,
      w: 2.0,
      h: 0.3,
      fontSize: 14,
      bold: true,
      color: C.navy,
      margin: 0,
    });
    ["微信视频号  ✅ 已支持", "抖音  账号管理就绪", "快手 / 小红书  持续扩展"].forEach((row, i) => {
      slide.addText(row, {
        x: 0.85,
        y: 1.85 + i * 0.65,
        w: 4.5,
        h: 0.4,
        fontSize: 13,
        color: C.dark,
        margin: 0,
      });
    });
    slide.addText("任务队列 · 状态跟踪 · 失败重试 · 发布前人工确认", {
      x: 0.85,
      y: 3.85,
      w: 4.5,
      h: 0.5,
      fontSize: 11,
      color: C.slate,
      margin: 0,
    });
    addCard(slide, { x: 5.85, y: 1.15, w: 3.6, h: 3.7, fill: C.light });
    addIconBadge(slide, icons.publish, 6.15, 1.45, C.navy);
    slide.addShape("rect", {
      x: 7.0,
      y: 2.2,
      w: 1.8,
      h: 1.8,
      fill: { color: C.white },
      line: { color: C.teal, width: 1 },
    });
    slide.addText("扫码登录", {
      x: 7.0,
      y: 4.15,
      w: 1.8,
      h: 0.3,
      fontSize: 11,
      color: C.navy,
      align: "center",
      margin: 0,
    });
    slide.addText("半自动发布 · 人工确认每一步", {
      x: 5.85,
      y: 4.95,
      w: 3.6,
      h: 0.3,
      fontSize: 12,
      bold: true,
      color: C.teal,
      align: "center",
      margin: 0,
    });
    addFooter(slide, 10);
    slide.addNotes("发布中心把最后一公里也纳入系统。坚持半自动而非全自动，关键发布动作保留人工确认，符合企业内控要求。");
  }

  // ── Slide 11: Compliance ──────────────────────────────────────
  {
    const slide = pres.addSlide();
    addLightBg(slide);
    addTitle(slide, "内置合规，降低发布风险");
    const layers = [
      { icon: icons.gavel, title: "内容合规", desc: "违禁词、敏感表述、夸大宣传检测" },
      { icon: icons.devices, title: "平台规则", desc: "标题长度、标签数量、格式自动校验" },
      { icon: icons.security, title: "发布审核", desc: "最后一道人工确认" },
    ];
    layers.forEach((l, i) => {
      const y = 1.2 + i * 1.35;
      addCard(slide, { x: 0.55, y, w: 5.2, h: 1.15 });
      addIconBadge(slide, l.icon, 0.75, y + 0.3, C.navy);
      slide.addText(l.title, {
        x: 1.45,
        y: y + 0.2,
        w: 2.5,
        h: 0.35,
        fontSize: 16,
        bold: true,
        color: C.navy,
        margin: 0,
      });
      slide.addText(l.desc, {
        x: 1.45,
        y: y + 0.58,
        w: 4.1,
        h: 0.45,
        fontSize: 12,
        color: C.slate,
        margin: 0,
      });
    });
    addCard(slide, { x: 6.0, y: 1.2, w: 3.45, h: 3.7 });
    slide.addText("✓  检测通过", {
      x: 6.2,
      y: 1.5,
      w: 3.0,
      h: 0.4,
      fontSize: 14,
      bold: true,
      color: C.mint,
      margin: 0,
    });
    slide.addText("✕  风险拦截", {
      x: 6.2,
      y: 2.2,
      w: 3.0,
      h: 0.4,
      fontSize: 14,
      bold: true,
      color: C.burgundy,
      margin: 0,
    });
    slide.addText("适用：品牌企业 · 政企客户 · 强监管行业", {
      x: 6.0,
      y: 4.55,
      w: 3.45,
      h: 0.5,
      fontSize: 11,
      color: C.slate,
      align: "center",
      margin: 0,
    });
    addFooter(slide, 11);
    slide.addNotes("合规与风控是企业采购时最看重的差异项。在前端把大部分低级风险拦下来，减少返工和限流问题。");
  }

  // ── Slide 12: Ease of Use ─────────────────────────────────────
  {
    const slide = pres.addSlide();
    addLightBg(slide);
    addTitle(slide, "无需技术背景，浏览器即用");
    const pages = [
      { icon: icons.web, title: "内容快做", desc: "单条内容快速处理" },
      { icon: icons.folder, title: "内容库", desc: "批量浏览与选题" },
      { icon: icons.publish, title: "发布中心", desc: "账号管理与发布" },
      { icon: icons.dashboard, title: "系统设置", desc: "模型、来源、账号配置" },
    ];
    pages.forEach((p, i) => {
      const x = 0.55 + (i % 2) * 4.7;
      const y = 1.15 + Math.floor(i / 2) * 1.85;
      addCard(slide, { x, y, w: 4.35, h: 1.55 });
      addIconBadge(slide, p.icon, x + 0.2, y + 0.45, C.navy);
      slide.addText(p.title, {
        x: x + 0.9,
        y: y + 0.35,
        w: 3.2,
        h: 0.35,
        fontSize: 17,
        bold: true,
        color: C.navy,
        margin: 0,
      });
      slide.addText(p.desc, {
        x: x + 0.9,
        y: y + 0.78,
        w: 3.1,
        h: 0.45,
        fontSize: 12,
        color: C.slate,
        margin: 0,
      });
    });
    slide.addText("低培训成本 · 低人员替换成本 · 不依赖单一技术同事", {
      x: 0.55,
      y: 5.0,
      w: 9,
      h: 0.3,
      fontSize: 14,
      bold: true,
      color: C.teal,
      align: "center",
      margin: 0,
    });
    addFooter(slide, 12);
    slide.addNotes("技术能力再强，如果只有技术同事能用，对企业价值就有限。全流程浏览器操作，运营人员即可日常使用。");
  }

  // ── Slide 13: Scenarios ───────────────────────────────────────
  {
    const slide = pres.addSlide();
    addLightBg(slide);
    addTitle(slide, "同一平台，支撑不同业务节奏", { size: 30 });
    const scenarios = [
      { title: "单条快发", who: "市场 / 运营", flow: "导入→生成→审核→发布", value: "热点快速响应", stat: "~5 分钟" },
      { title: "批量日更", who: "内容团队", flow: "选题→批量生成→排期发布", value: "产能倍增", stat: "10+ 条/天" },
      { title: "专题品牌", who: "品牌 / 公关", flow: "定制素材+模板→专题成片", value: "品牌一致性", stat: "统一视觉" },
    ];
    scenarios.forEach((s, i) => {
      const x = 0.55 + i * 3.1;
      addCard(slide, { x, y: 1.1, w: 2.85, h: 3.85, fill: i === 1 ? C.navy : C.light });
      const tc = i === 1 ? C.white : C.navy;
      const sc = i === 1 ? C.ice : C.slate;
      slide.addText(s.title, {
        x,
        y: 1.25,
        w: 2.85,
        h: 0.4,
        fontSize: 16,
        bold: true,
        color: tc,
        align: "center",
        margin: 0,
      });
      slide.addText(s.stat, {
        x,
        y: 1.75,
        w: 2.85,
        h: 0.55,
        fontSize: 22,
        bold: true,
        color: i === 1 ? C.mint : C.teal,
        align: "center",
        margin: 0,
      });
      slide.addText(`部门：${s.who}`, {
        x: x + 0.15,
        y: 2.45,
        w: 2.55,
        h: 0.3,
        fontSize: 11,
        color: sc,
        margin: 0,
      });
      slide.addText(`流程：${s.flow}`, {
        x: x + 0.15,
        y: 2.85,
        w: 2.55,
        h: 0.55,
        fontSize: 10,
        color: sc,
        margin: 0,
      });
      slide.addText(s.value, {
        x,
        y: 4.35,
        w: 2.85,
        h: 0.35,
        fontSize: 13,
        bold: true,
        color: i === 1 ? C.mint : C.teal,
        align: "center",
        margin: 0,
      });
    });
    addFooter(slide, 13);
    slide.addNotes("同一套平台支撑不同部门、不同节奏的内容需求。采购时可以理解成一套系统覆盖多种业务场景。");
  }

  // ── Slide 14: Demo ────────────────────────────────────────────
  {
    const slide = pres.addSlide();
    addDarkBg(slide);
    slide.addText("三分钟，看完整流程", {
      x: 0.6,
      y: 0.5,
      w: 8.8,
      h: 0.8,
      fontFace: "Cambria",
      fontSize: 36,
      bold: true,
      color: C.white,
      margin: 0,
    });
    const demoSteps = ["导入内容", "生成文案", "合成视频", "发布流程"];
    demoSteps.forEach((s, i) => {
      const x = 0.7 + i * 2.3;
      slide.addShape("ellipse", {
        x: x + 0.55,
        y: 1.8,
        w: 0.7,
        h: 0.7,
        fill: { color: C.teal },
        line: { color: C.teal, width: 0 },
      });
      slide.addText(String(i + 1), {
        x: x + 0.55,
        y: 1.95,
        w: 0.7,
        h: 0.4,
        fontSize: 20,
        bold: true,
        color: C.white,
        align: "center",
        margin: 0,
      });
      slide.addText(s, {
        x,
        y: 2.65,
        w: 1.8,
        h: 0.4,
        fontSize: 14,
        color: C.ice,
        align: "center",
        margin: 0,
      });
      if (i < 3) {
        slide.addShape("rightArrow", {
          x: x + 1.85,
          y: 2.05,
          w: 0.35,
          h: 0.2,
          fill: { color: C.ice },
          line: { color: C.ice, width: 0 },
        });
      }
    });
    slide.addText("请关注：操作是否简单？  速度是否够快？", {
      x: 0.6,
      y: 3.6,
      w: 8.8,
      h: 0.5,
      fontSize: 20,
      color: C.mint,
      align: "center",
      margin: 0,
    });
    slide.addText("建议现场演示或播放录屏备份", {
      x: 0.6,
      y: 4.85,
      w: 8.8,
      h: 0.3,
      fontSize: 12,
      color: C.ice,
      align: "center",
      margin: 0,
    });
    addFooter(slide, 14, 18, C.ice);
    slide.addNotes("演示：导入一篇普通内容，一键生成文案，自动合成竖屏视频，打开发布中心展示扫码发布流程。重点关注操作是否简单、速度是否够快。");
  }

  // ── Slide 15: Architecture ────────────────────────────────────
  {
    const slide = pres.addSlide();
    addLightBg(slide);
    addTitle(slide, "可扩展、可管控、可私有化");
    const layers = [
      { name: "操作层", desc: "Web 可视化界面", color: C.teal },
      { name: "业务层", desc: "采集 · 加工 · 视频 · 发布", color: C.navy },
      { name: "能力层", desc: "多模型 AI · 视觉 · 语音", color: C.graphite },
      { name: "数据层", desc: "本地存储，企业自主掌控", color: C.slate },
    ];
    layers.forEach((l, i) => {
      const y = 1.15 + i * 0.95;
      slide.addShape("roundRect", {
        x: 0.55,
        y,
        w: 5.5,
        h: 0.75,
        fill: { color: l.color },
        line: { color: l.color, width: 0 },
        rectRadius: 0.06,
      });
      slide.addText(l.name, {
        x: 0.75,
        y: y + 0.1,
        w: 1.2,
        h: 0.55,
        fontSize: 14,
        bold: true,
        color: C.white,
        margin: 0,
      });
      slide.addText(l.desc, {
        x: 2.0,
        y: y + 0.18,
        w: 3.8,
        h: 0.4,
        fontSize: 12,
        color: C.ice,
        margin: 0,
      });
    });
    const kw = [
      { icon: icons.hub, text: "模块化" },
      { icon: icons.extension, text: "不绑定单一厂商" },
      { icon: icons.shield, text: "支持定制扩展" },
    ];
    kw.forEach((k, i) => {
      const y = 1.35 + i * 1.15;
      addCard(slide, { x: 6.35, y, w: 3.1, h: 0.9 });
      addIconBadge(slide, k.icon, 6.55, y + 0.18, C.navy);
      slide.addText(k.text, {
        x: 7.25,
        y: y + 0.28,
        w: 2.0,
        h: 0.4,
        fontSize: 14,
        bold: true,
        color: C.navy,
        margin: 0,
      });
    });
    addFooter(slide, 15);
    slide.addNotes("模块化架构，可私有化部署，不绑定单一AI厂商。对企业采购来说，是可交付、可运维、可扩展的内容生产系统。");
  }

  // ── Slide 16: Procurement Metrics ─────────────────────────────
  {
    const slide = pres.addSlide();
    addLightBg(slide);
    addTitle(slide, "用五个指标衡量价值");
    const metrics = [
      { icon: icons.speed, label: "效率", desc: "单条制作\n小时级→分钟级" },
      { icon: icons.savings, label: "成本", desc: "减少重复人工\n提升人产能" },
      { icon: icons.shield, label: "风险", desc: "内置合规\n降低事故概率" },
      { icon: icons.extension, label: "扩展", desc: "来源/平台/模型\n可配置扩展" },
      { icon: icons.rocket, label: "落地", desc: "快速上手\n缩短价值周期" },
    ];
    metrics.forEach((m, i) => {
      const x = 0.45 + i * 1.88;
      const y = 1.15;
      addCard(slide, { x, y, w: 1.72, h: 3.85 });
      addIconBadge(slide, m.icon, x + 0.58, y + 0.35, C.navy);
      slide.addText(m.label, {
        x,
        y: y + 1.1,
        w: 1.72,
        h: 0.4,
        fontSize: 16,
        bold: true,
        color: C.navy,
        align: "center",
        margin: 0,
      });
      slide.addText(m.desc, {
        x: x + 0.1,
        y: y + 1.65,
        w: 1.52,
        h: 1.8,
        fontSize: 11,
        color: C.slate,
        align: "center",
        margin: 0,
      });
    });
    addFooter(slide, 16);
    slide.addNotes("用效率、成本、风险、扩展、落地五个指标评估。这比用了什么模型更能帮助采购决策。");
  }

  // ── Slide 17: Implementation ────────────────────────────────────
  {
    const slide = pres.addSlide();
    addLightBg(slide);
    addTitle(slide, "分阶段落地，降低采购风险");
    const phases = [
      { phase: "试点验证", time: "1–2 周", goal: "部署环境，接入 1–2 个来源，跑通 1 个平台" },
      { phase: "推广使用", time: "约 1 个月", goal: "培训团队，建立选题与发布 SOP" },
      { phase: "规模扩展", time: "持续", goal: "新增来源、平台、品牌定制" },
    ];
    phases.forEach((p, i) => {
      const x = 0.55 + i * 3.1;
      addCard(slide, { x, y: 1.15, w: 2.85, h: 3.2, fill: i === 0 ? C.navy : C.light });
      const tc = i === 0 ? C.white : C.navy;
      const sc = i === 0 ? C.ice : C.slate;
      slide.addText(p.phase, {
        x,
        y: 1.3,
        w: 2.85,
        h: 0.4,
        fontSize: 16,
        bold: true,
        color: tc,
        align: "center",
        margin: 0,
      });
      slide.addText(p.time, {
        x,
        y: 1.8,
        w: 2.85,
        h: 0.35,
        fontSize: 13,
        color: i === 0 ? C.mint : C.teal,
        align: "center",
        margin: 0,
      });
      slide.addText(p.goal, {
        x: x + 0.15,
        y: 2.35,
        w: 2.55,
        h: 1.6,
        fontSize: 11,
        color: sc,
        margin: 0,
      });
      if (i < 2) {
        slide.addShape("rightArrow", {
          x: x + 2.9,
          y: 2.5,
          w: 0.15,
          h: 0.2,
          fill: { color: C.teal },
          line: { color: C.teal, width: 0 },
        });
      }
    });
    slide.addText("合作方式：私有化部署 · 按需定制 · 运维支持", {
      x: 0.55,
      y: 4.55,
      w: 9,
      h: 0.4,
      fontSize: 14,
      bold: true,
      color: C.teal,
      align: "center",
      margin: 0,
    });
    addIconBadge(slide, icons.handshake, 4.65, 4.95, C.teal);
    addFooter(slide, 17);
    slide.addNotes("建议分阶段落地：先试点验证ROI，再推广使用，最后规模扩展。先小范围验证，再扩大投入。");
  }

  // ── Slide 18: Closing ───────────────────────────────────────────
  {
    const slide = pres.addSlide();
    addDarkBg(slide);
    slide.addText("让内容生产，像流水线一样高效", {
      x: 0.6,
      y: 0.7,
      w: 8.8,
      h: 0.8,
      fontFace: "Cambria",
      fontSize: 34,
      bold: true,
      color: C.white,
      margin: 0,
    });
    slide.addText(
      bulletItems(
        [
          "多源接入，不限资讯类型与素材形态",
          "全流程自动化，业务人员即可独立操作",
          "合规内置，兼顾效率与风控",
        ],
        C.ice,
        16
      ),
      { x: 0.7, y: 1.75, w: 8.5, h: 1.8, margin: 0 }
    );
    addCard(slide, { x: 0.6, y: 3.55, w: 8.8, h: 1.15, fill: C.graphite });
    slide.addShape("roundRect", {
      x: 0.6,
      y: 3.55,
      w: 8.8,
      h: 1.15,
      fill: { color: C.teal, transparency: 100 },
      line: { color: C.teal, width: 1 },
      rectRadius: 0.08,
    });
    slide.addText("建议下一步：预约试点验证 · 提供样例内容试做 · 安排技术对接会议", {
      x: 0.8,
      y: 3.85,
      w: 8.4,
      h: 0.55,
      fontSize: 15,
      bold: true,
      color: C.mint,
      align: "center",
      margin: 0,
    });
    slide.addText("[联系人] · [电话] · [邮箱]", {
      x: 0.6,
      y: 4.95,
      w: 8.8,
      h: 0.35,
      fontSize: 13,
      color: C.ice,
      align: "center",
      margin: 0,
    });
    slide.addNotes("总结三句话。建议用贵司真实内容做一次试点验证。谢谢各位。");
  }

  await pres.writeFile({ fileName: OUT });
  console.log("Wrote:", OUT);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
