import http from "node:http";
import { URL } from "node:url";

const port = Number(process.env.PORT || 18081);
const mcpProtocolVersion = "2025-03-26";

const equipmentProfiles = {
  "EQ-CNC-650-01": {
    equipment_id: "EQ-CNC-650-01",
    name: "CNC 加工中心 1#",
    model: "CNC-650",
    line_code: "LINE-MACHINING-A",
    station_code: "ST-CNC-01",
    location: "机加工车间 A 线",
    vendor: "Nanjing Precision Machine",
  },
  "EQ-IM-220T-03": {
    equipment_id: "EQ-IM-220T-03",
    name: "220T 注塑机 3#",
    model: "IM-220T",
    line_code: "LINE-INJECTION-B",
    station_code: "ST-IM-03",
    location: "注塑车间 B 线",
    vendor: "Haitian",
  },
  "EQ-PACK-01": {
    equipment_id: "EQ-PACK-01",
    name: "自动包装线 1#",
    model: "PKG-AUTO-01",
    line_code: "LINE-PACKING-A",
    station_code: "ST-PACK-01",
    location: "包装车间 A 线",
    vendor: "Suzhou Automation",
  },
};

const workOrderFixtures = [
  {
    work_order_id: "WO-20260418-0017",
    equipment_id: "EQ-CNC-650-01",
    fault_code: "AX-203",
    status: "closed",
    priority: "high",
    created_at: "2026-04-18T08:42:00+08:00",
    closed_at: "2026-04-18T10:05:00+08:00",
    downtime_minutes: 83,
    technician: "维修一组",
    symptom: "X 轴伺服过载报警，主轴停止，当前工件批次暂停。",
    root_cause: "X 轴丝杆防护罩积屑导致导轨阻力升高，伺服负载持续超过阈值。",
    actions: [
      "清理 X 轴导轨与丝杆防护罩积屑",
      "检查润滑泵出油状态并补充润滑脂",
      "复位伺服驱动器并低速空跑 15 分钟",
    ],
    parts_used: [
      { part_no: "LUBE-GR-2", name: "2# 锂基润滑脂", quantity: 1, unit: "支" },
    ],
    follow_up: "建议下次周保增加 X 轴防护罩清洁项。",
  },
  {
    work_order_id: "WO-20260415-0042",
    equipment_id: "EQ-CNC-650-01",
    fault_code: "SP-118",
    status: "closed",
    priority: "medium",
    created_at: "2026-04-15T14:16:00+08:00",
    closed_at: "2026-04-15T15:02:00+08:00",
    downtime_minutes: 46,
    technician: "维修二组",
    symptom: "主轴温升偏高，连续加工 40 分钟后温度超过 68°C。",
    root_cause: "冷却风道滤网堵塞，主轴散热效率下降。",
    actions: ["拆洗主轴冷却风道滤网", "检查冷却风扇电流", "恢复加工并观察温升曲线"],
    parts_used: [
      { part_no: "FILTER-CNC-650-AIR", name: "CNC-650 主轴风道滤网", quantity: 1, unit: "片" },
    ],
    follow_up: "滤网剩余库存低于安全库存，建议补货。",
  },
  {
    work_order_id: "WO-20260412-0029",
    equipment_id: "EQ-IM-220T-03",
    fault_code: "HT-407",
    status: "closed",
    priority: "high",
    created_at: "2026-04-12T21:08:00+08:00",
    closed_at: "2026-04-12T22:31:00+08:00",
    downtime_minutes: 83,
    technician: "夜班维修",
    symptom: "料筒三区温度波动超过 ±12°C，产品出现短射。",
    root_cause: "三区热电偶接线端子松动，温控反馈不稳定。",
    actions: ["停机断电后紧固端子", "校验热电偶反馈值", "首件确认后恢复生产"],
    parts_used: [],
    follow_up: "建议月保检查料筒各区接线端子紧固状态。",
  },
  {
    work_order_id: "WO-20260410-0008",
    equipment_id: "EQ-PACK-01",
    fault_code: "PK-052",
    status: "closed",
    priority: "medium",
    created_at: "2026-04-10T09:20:00+08:00",
    closed_at: "2026-04-10T10:10:00+08:00",
    downtime_minutes: 50,
    technician: "自动化小组",
    symptom: "封箱机入口光电误触发，包装线频繁暂停。",
    root_cause: "光电传感器镜面有胶带残留，灵敏度漂移。",
    actions: ["清洁光电镜面", "重新标定触发距离", "连续运行 30 分钟确认无误停"],
    parts_used: [],
    follow_up: "建议换班点检增加光电镜面清洁确认。",
  },
];

const alarmFixtures = [
  {
    alarm_id: "ALM-20260418-083901",
    equipment_id: "EQ-CNC-650-01",
    code: "AX-203",
    severity: "high",
    message: "X 轴伺服负载超过 120%，持续 8 秒。",
    occurred_at: "2026-04-18T08:39:01+08:00",
    cleared_at: "2026-04-18T09:58:44+08:00",
    tag: "CNC650_AXIS_X_LOAD",
    value: 126.4,
    unit: "%",
  },
  {
    alarm_id: "ALM-20260418-084022",
    equipment_id: "EQ-CNC-650-01",
    code: "LUBE-014",
    severity: "medium",
    message: "导轨润滑压力低于下限。",
    occurred_at: "2026-04-18T08:40:22+08:00",
    cleared_at: "2026-04-18T09:12:07+08:00",
    tag: "CNC650_LUBE_PRESSURE",
    value: 0.18,
    unit: "MPa",
  },
  {
    alarm_id: "ALM-20260418-084811",
    equipment_id: "EQ-CNC-650-01",
    code: "SP-118",
    severity: "medium",
    message: "主轴温度超过预警阈值 68°C。", 
    occurred_at: "2026-04-18T08:48:11+08:00",
    cleared_at: "2026-04-18T09:21:36+08:00",
    tag: "CNC650_SPINDLE_TEMP",
    value: 70.2,
    unit: "°C",
  },
  {
    alarm_id: "ALM-20260418-085720",
    equipment_id: "EQ-CNC-650-01",
    code: "AX-203",
    severity: "high",
    message: "X 轴伺服负载再次超过 115%，建议复核导轨阻力与润滑状态。",
    occurred_at: "2026-04-18T08:57:20+08:00",
    cleared_at: null,
    tag: "CNC650_AXIS_X_LOAD",
    value: 118.9,
    unit: "%",
  },
  {
    alarm_id: "ALM-20260412-210611",
    equipment_id: "EQ-IM-220T-03",
    code: "HT-407",
    severity: "high",
    message: "料筒三区温度偏差超过控制上限。",
    occurred_at: "2026-04-12T21:06:11+08:00",
    cleared_at: "2026-04-12T22:20:03+08:00",
    tag: "IM220T_BARREL_ZONE3_TEMP",
    value: 224.7,
    unit: "°C",
  },
  {
    alarm_id: "ALM-20260412-211004",
    equipment_id: "EQ-IM-220T-03",
    code: "PRS-022",
    severity: "medium",
    message: "注射压力波动超过设定范围，连续 3 个周期触发。",
    occurred_at: "2026-04-12T21:10:04+08:00",
    cleared_at: "2026-04-12T21:38:18+08:00",
    tag: "IM220T_INJECTION_PRESSURE",
    value: 14.8,
    unit: "MPa",
  },
  {
    alarm_id: "ALM-20260412-212945",
    equipment_id: "EQ-IM-220T-03",
    code: "HT-407",
    severity: "critical",
    message: "料筒三区温度反馈丢失，温控回路进入保护。",
    occurred_at: "2026-04-12T21:29:45+08:00",
    cleared_at: "2026-04-12T22:20:03+08:00",
    tag: "IM220T_BARREL_ZONE3_SENSOR",
    value: null,
    unit: "",
  },
  {
    alarm_id: "ALM-20260410-091855",
    equipment_id: "EQ-PACK-01",
    code: "PK-052",
    severity: "medium",
    message: "入口光电传感器触发频率异常。",
    occurred_at: "2026-04-10T09:18:55+08:00",
    cleared_at: "2026-04-10T10:01:12+08:00",
    tag: "PACK_INLET_PHOTOEYE",
    value: 17,
    unit: "times/min",
  },
  {
    alarm_id: "ALM-20260410-092601",
    equipment_id: "EQ-PACK-01",
    code: "PK-061",
    severity: "low",
    message: "输送带速度短时低于设定值。",
    occurred_at: "2026-04-10T09:26:01+08:00",
    cleared_at: "2026-04-10T09:27:40+08:00",
    tag: "PACK_CONVEYOR_SPEED",
    value: 0.62,
    unit: "m/s",
  },
  {
    alarm_id: "ALM-20260410-093204",
    equipment_id: "EQ-PACK-01",
    code: "PK-052",
    severity: "medium",
    message: "入口光电传感器连续抖动，疑似镜面污染或位置偏移。",
    occurred_at: "2026-04-10T09:32:04+08:00",
    cleared_at: null,
    tag: "PACK_INLET_PHOTOEYE",
    value: 21,
    unit: "times/min",
  },
];

const sparePartFixtures = [
  {
    part_no: "BRG-6205-2RS",
    name: "深沟球轴承 6205-2RS",
    category: "bearing",
    equipment_models: ["CNC-650", "PKG-AUTO-01"],
    available_quantity: 12,
    safety_stock: 6,
    warehouse_code: "WH-MRO-01",
    location_bin: "A-03-12",
    unit: "只",
    supplier: "Shanghai Bearing Supply",
    lead_time_days: 5,
  },
  {
    part_no: "FILTER-CNC-650-AIR",
    name: "CNC-650 主轴风道滤网",
    category: "filter",
    equipment_models: ["CNC-650"],
    available_quantity: 2,
    safety_stock: 4,
    warehouse_code: "WH-MRO-01",
    location_bin: "B-02-08",
    unit: "片",
    supplier: "Nanjing Precision Machine",
    lead_time_days: 10,
  },
  {
    part_no: "TC-K-3M-M6",
    name: "K 型热电偶 3m M6 螺纹",
    category: "sensor",
    equipment_models: ["IM-220T"],
    available_quantity: 8,
    safety_stock: 4,
    warehouse_code: "WH-MRO-02",
    location_bin: "S-01-04",
    unit: "根",
    supplier: "Suzhou Sensor Tech",
    lead_time_days: 3,
  },
  {
    part_no: "PE-SENSOR-M18-NPN",
    name: "M18 NPN 漫反射光电传感器",
    category: "sensor",
    equipment_models: ["PKG-AUTO-01"],
    available_quantity: 5,
    safety_stock: 3,
    warehouse_code: "WH-MRO-02",
    location_bin: "S-04-02",
    unit: "个",
    supplier: "Omron Compatible Supply",
    lead_time_days: 7,
  },
];

const alternativePartFixtures = {
  "FILTER-CNC-650-AIR": [
    {
      part_no: "FILTER-CNC-650-AIR-ALT",
      name: "CNC-650 主轴风道滤网兼容件",
      compatible: true,
      limitation: "需要确认滤网边框厚度，建议由维修主管复核。",
      available_quantity: 6,
      warehouse_code: "WH-MRO-01",
    },
  ],
  "PE-SENSOR-M18-NPN": [
    {
      part_no: "PE-SENSOR-M18-PNP",
      name: "M18 PNP 漫反射光电传感器",
      compatible: false,
      limitation: "输出类型不同，需同步调整输入模块接线，不建议直接替代。",
      available_quantity: 9,
      warehouse_code: "WH-MRO-02",
    },
  ],
};

function sendJson(res, status, payload, extraHeaders = {}) {
  const body = payload === null ? "" : JSON.stringify(payload, null, 2);
  res.writeHead(status, {
    "Content-Type": "application/json; charset=utf-8",
    "Content-Length": Buffer.byteLength(body),
    ...extraHeaders,
  });
  res.end(body);
}

function readJson(req) {
  return new Promise((resolve, reject) => {
    let raw = "";
    req.on("data", (chunk) => {
      raw += chunk;
      if (raw.length > 1024 * 1024) {
        reject(new Error("REQUEST_TOO_LARGE"));
        req.destroy();
      }
    });
    req.on("end", () => {
      if (!raw.trim()) {
        resolve({});
        return;
      }
      try {
        resolve(JSON.parse(raw));
      } catch (error) {
        reject(error);
      }
    });
  });
}

function requireAuth(req, res, { jsonRpc = false } = {}) {
  const authorization = req.headers.authorization || "";
  if (authorization.startsWith("Bearer ")) {
    return true;
  }
  if (jsonRpc) {
    sendJson(res, 401, {
      jsonrpc: "2.0",
      error: {
        code: -32001,
        message: "示例 MCP 接口需要 Authorization: Bearer <token>。",
      },
    });
    return false;
  }
  sendJson(res, 401, {
    error: {
      code: "AUTH_REQUIRED",
      message: "示例 HTTP 接口需要 Authorization: Bearer <token>。",
    },
  });
  return false;
}

function simulatedMeta() {
  return {
    simulated: true,
    notice: "示例模拟返回，仅用于本地联调，不代表真实业务数据、真实接口返回或真实生产记录。",
  };
}

function makeWorkOrders({ equipmentId, faultCode }) {
  return workOrderFixtures.filter((item) => {
    if (equipmentId && item.equipment_id !== equipmentId) {
      return false;
    }
    if (faultCode && item.fault_code !== faultCode) {
      return false;
    }
    return true;
  });
}

function makeEquipment({ equipmentId, keyword }) {
  const normalizedKeyword = String(keyword || "").trim().toLowerCase();
  const items = Object.values(equipmentProfiles).filter((item) => {
    if (equipmentId && item.equipment_id !== equipmentId) {
      return false;
    }
    if (normalizedKeyword) {
      return (
        item.equipment_id.toLowerCase().includes(normalizedKeyword) ||
        item.name.toLowerCase().includes(normalizedKeyword) ||
        item.model.toLowerCase().includes(normalizedKeyword) ||
        item.line_code.toLowerCase().includes(normalizedKeyword) ||
        item.location.toLowerCase().includes(normalizedKeyword)
      );
    }
    return true;
  });
  return {
    item: equipmentId ? items[0] || null : null,
    items,
    total: items.length,
  };
}

function makeAlarms({ equipmentId, severity }) {
  return alarmFixtures.filter((item) => {
    if (equipmentId && item.equipment_id !== equipmentId) {
      return false;
    }
    if (severity && item.severity !== severity) {
      return false;
    }
    return true;
  });
}

function makeSpareParts({ partNo, keyword }) {
  const normalizedKeyword = String(keyword || "").trim().toLowerCase();
  const items = sparePartFixtures.filter((item) => {
    if (partNo && item.part_no !== partNo) {
      return false;
    }
    if (normalizedKeyword) {
      return (
        item.part_no.toLowerCase().includes(normalizedKeyword) ||
        item.name.toLowerCase().includes(normalizedKeyword) ||
        item.category.toLowerCase().includes(normalizedKeyword)
      );
    }
    return true;
  });
  const selected = items.length > 0 ? items : sparePartFixtures.slice(0, 2);
  const alternatives = selected.flatMap((item) => alternativePartFixtures[item.part_no] || []);
  return {
    items: selected,
    alternatives,
  };
}

function jsonRpcResult(id, payload, headers = {}) {
  return {
    status: 200,
    headers,
    body: {
      jsonrpc: "2.0",
      id,
      result: payload,
    },
  };
}

function jsonRpcError(id, code, message) {
  return {
    status: 200,
    body: {
      jsonrpc: "2.0",
      id,
      error: { code, message },
    },
  };
}

function callMcpTool(name, args) {
  if (name === "work_order.history") {
    const workorders = makeWorkOrders({
      equipmentId: args.equipment_id,
      faultCode: args.fault_code,
    });
    return {
      structuredContent: {
        workorders,
        total: workorders.length,
        _meta: simulatedMeta(),
      },
    };
  }
  if (name === "equipment.lookup") {
    return {
      structuredContent: {
        ...makeEquipment({
          equipmentId: args.equipment_id,
          keyword: args.query,
        }),
        _meta: simulatedMeta(),
      },
    };
  }
  if (name === "work_order.draft.create") {
    const equipment = equipmentProfiles[args.equipment_id] || {
      equipment_id: args.equipment_id || "equipment-placeholder",
      name: "未知设备",
      line_code: "LINE-UNKNOWN",
      location: "未知位置",
    };
    return {
      structuredContent: {
        draft_id: `mock-draft-${Buffer.from(String(args.equipment_id || "equipment")).toString("hex").slice(0, 8)}`,
        status: "draft",
        title: args.summary || "设备异常待处理",
        priority: args.priority || "medium",
        equipment,
        suggested_assignee_group: args.priority === "high" ? "维修一组" : "值班维修",
        approval_required: true,
        url: "https://maintenance.example.local/workorders/drafts/mock-draft",
        _meta: simulatedMeta(),
      },
    };
  }
  if (name === "alarm.query") {
    const alarms = makeAlarms({
      equipmentId: args.equipment_id,
      severity: args.severity,
    });
    return {
      structuredContent: {
        alarms,
        total: alarms.length,
        _meta: simulatedMeta(),
      },
    };
  }
  if (name === "spare_parts.lookup") {
    return {
      structuredContent: {
        ...makeSpareParts({
          partNo: args.part_no,
          keyword: args.keyword,
        }),
        _meta: simulatedMeta(),
      },
    };
  }
  return null;
}

function handleJsonRpc(payload) {
  const { id, method, params } = payload;

  if (method === "initialize") {
    return jsonRpcResult(
      id,
      {
        protocolVersion: mcpProtocolVersion,
        capabilities: { tools: {} },
        serverInfo: {
          name: "mfg-maintenance-upstream-example",
          version: "1.0.0",
        },
      },
      { "Mcp-Session-Id": "mock-session" },
    );
  }

  if (method === "notifications/initialized") {
    return { status: 202, body: null };
  }

  if (method === "tools/list") {
    return jsonRpcResult(id, {
      tools: [
        { name: "equipment.lookup", description: "查询模拟设备台账。" },
        { name: "work_order.history", description: "查询模拟历史维修工单。" },
        { name: "work_order.draft.create", description: "创建模拟维修工单草稿。" },
        { name: "alarm.query", description: "查询模拟设备报警流水。" },
        { name: "spare_parts.lookup", description: "查询模拟备件目录。" },
      ],
    });
  }

  if (method === "tools/call") {
    const toolResult = callMcpTool(params?.name, params?.arguments || {});
    if (toolResult) {
      return jsonRpcResult(id, toolResult);
    }
    return jsonRpcError(id, -32601, `Unknown example tool: ${params?.name || ""}`);
  }

  return jsonRpcError(id, -32601, `Unknown method: ${method || ""}`);
}

async function handleMcp(req, res) {
  if (req.method !== "POST") {
    sendJson(res, 405, {
      error: {
        code: "METHOD_NOT_ALLOWED",
        message: "示例 MCP Endpoint 为 POST /mcp。",
      },
    });
    return;
  }
  if (!requireAuth(req, res, { jsonRpc: true })) {
    return;
  }
  try {
    const payload = await readJson(req);
    const response = handleJsonRpc(payload);
    sendJson(res, response.status, response.body, response.headers);
  } catch (error) {
    sendJson(res, 400, {
      jsonrpc: "2.0",
      error: {
        code: -32700,
        message: error instanceof Error ? error.message : "Invalid JSON-RPC request",
      },
    });
  }
}

async function handleRest(req, res, url) {
  if (!requireAuth(req, res)) {
    return;
  }

  if (req.method === "GET" && url.pathname === "/api/v1/workorders") {
    const workorders = makeWorkOrders({
      equipmentId: url.searchParams.get("equipment_id"),
      faultCode: url.searchParams.get("fault_code"),
    });
    sendJson(res, 200, {
      data: {
        items: workorders,
        total: workorders.length,
      },
      _meta: simulatedMeta(),
    });
    return;
  }

  if (req.method === "GET" && url.pathname === "/api/v1/equipment") {
    sendJson(res, 200, {
      data: makeEquipment({
        equipmentId: url.searchParams.get("equipment_id"),
        keyword: url.searchParams.get("keyword"),
      }),
      _meta: simulatedMeta(),
    });
    return;
  }

  if (req.method === "POST" && url.pathname === "/api/v1/workorders/drafts") {
    const body = await readJson(req);
    const equipment = equipmentProfiles[body.equipment_id] || {
      equipment_id: body.equipment_id || "equipment-placeholder",
      name: "未知设备",
      line_code: "LINE-UNKNOWN",
      location: "未知位置",
    };
    const draftId = `mock-draft-${Buffer.from(String(body.equipment_id || "equipment")).toString("hex").slice(0, 8)}`;
    sendJson(res, 200, {
      data: {
        id: draftId,
        status: "draft",
        title: body.title || "设备异常待处理",
        priority: body.priority || "medium",
        equipment,
        suggested_assignee_group: body.priority === "high" ? "维修一组" : "值班维修",
        approval_required: true,
        idempotency_key: req.headers["idempotency-key"] || null,
        url: `https://maintenance.example.local/workorders/drafts/${draftId}`,
      },
      _meta: simulatedMeta(),
    });
    return;
  }

  if (req.method === "GET" && url.pathname === "/api/v1/alarms") {
    const alarms = makeAlarms({
      equipmentId: url.searchParams.get("equipment_id"),
      severity: url.searchParams.get("severity"),
    });
    sendJson(res, 200, {
      data: {
        items: alarms,
        total: alarms.length,
      },
      _meta: simulatedMeta(),
    });
    return;
  }

  if (req.method === "GET" && url.pathname === "/api/v1/spare-parts") {
    sendJson(res, 200, {
      data: makeSpareParts({
        partNo: url.searchParams.get("part_no"),
        keyword: url.searchParams.get("keyword"),
      }),
      _meta: simulatedMeta(),
    });
    return;
  }

  sendJson(res, 404, {
    error: {
      code: "NOT_FOUND",
      message: "示例 HTTP 接口不存在。",
    },
  });
}

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url || "/", `http://${req.headers.host || "127.0.0.1"}`);

  if (req.method === "GET" && url.pathname === "/healthz") {
    sendJson(res, 200, {
      status: "ok",
      service: "mfg-maintenance-upstream-example",
      rest_base_url: `http://127.0.0.1:${port}`,
      mcp_endpoint: `http://127.0.0.1:${port}/mcp`,
    });
    return;
  }

  if (url.pathname === "/mcp") {
    await handleMcp(req, res);
    return;
  }

  await handleRest(req, res, url);
});

server.listen(port, "127.0.0.1", () => {
  console.log(`Manufacturing maintenance upstream example listening on http://127.0.0.1:${port}`);
  console.log(`REST base URL: http://127.0.0.1:${port}`);
  console.log(`MCP endpoint:  http://127.0.0.1:${port}/mcp`);
});
