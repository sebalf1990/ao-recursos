#!/usr/bin/env node
"use strict";

const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..", "..", "..");
const RES = path.join(ROOT, "dev", "Recursos");
const MAPS = path.join(RES, "Mapas");
const DAT = path.join(RES, "Dat");
const INIT = path.join(RES, "init");

const WATER_GRHS = [
  [1505, 1520],
  [124, 139],
  [24223, 24238],
  [24303, 24318],
  [468, 483],
  [44668, 44683],
  [24143, 24158],
  [12628, 12643],
  [2948, 2963],
];

const MINERALS = new Map([
  [3391, "Carbon"],
  [192, "Hierro"],
  [193, "Plata"],
  [194, "Oro"],
  [3787, "Blodium"],
]);

function readCp1252(file) {
  return fs.readFileSync(file, "latin1");
}

function parseDatSections(file, prefix) {
  const text = readCp1252(file);
  const rx = new RegExp(`^\\[${prefix}(\\d+)\\][^\\r\\n]*\\r?\\n([\\s\\S]*?)(?=^\\[${prefix}\\d+\\]|$(?![\\s\\S]))`, "gmi");
  const result = new Map();
  let m;
  while ((m = rx.exec(text)) !== null) {
    const id = Number(m[1]);
    const body = m[2];
    const data = {};
    for (const line of body.split(/\r?\n/)) {
      const idx = line.indexOf("=");
      if (idx < 0) continue;
      const key = line.slice(0, idx).trim().toLowerCase();
      const value = line.slice(idx + 1).trim();
      if (!(key in data)) data[key] = value;
    }
    result.set(id, data);
  }
  return result;
}

function num(value, fallback = 0) {
  const n = Number.parseInt(value ?? "", 10);
  return Number.isFinite(n) ? n : fallback;
}

function parseObjects() {
  return parseDatSections(path.join(DAT, "obj.dat"), "OBJ");
}

function parseNpcs() {
  return parseDatSections(path.join(DAT, "NPCs.dat"), "NPC");
}

function classifyObjects(objects) {
  const trees = [];
  const oreDepositsByMineral = new Map();
  const anvils = [];
  const forges = [];
  const fishingPools = [];

  for (const [id, obj] of objects) {
    const type = num(obj.objtype);
    const name = obj.name ?? "";
    if (type === 4) trees.push(id);
    if (type === 22 && /^yacimiento/i.test(name)) {
      const mineral = num(obj.mineralindex);
      if (MINERALS.has(mineral) && !oreDepositsByMineral.has(mineral)) {
        oreDepositsByMineral.set(mineral, id);
      }
    }
    if (type === 27) anvils.push(id);
    if (type === 28) forges.push(id);
    if (type === 52) fishingPools.push(id);
  }

  return { trees, oreDepositsByMineral, anvils, forges, fishingPools };
}

function parseGrhIndex(file) {
  const b = fs.readFileSync(file);
  let o = 0;
  const readI16 = () => {
    const v = b.readInt16LE(o);
    o += 2;
    return v;
  };
  const readI32 = () => {
    const v = b.readInt32LE(o);
    o += 4;
    return v;
  };
  const readF32 = () => {
    const v = b.readFloatLE(o);
    o += 4;
    return v;
  };

  const version = readI32();
  const count = readI32();
  const grhs = new Map();
  while (o < b.length) {
    const id = readI32();
    const frames = readI16();
    if (frames <= 0) throw new Error(`Invalid NumFrames for GRH ${id}`);
    const rec = { frames, fileNum: 0, width: 0, height: 0, speed: 0 };
    if (frames > 1) {
      rec.frameIds = [];
      for (let i = 0; i < frames; i++) rec.frameIds.push(readI32());
      rec.speed = readF32();
      const first = grhs.get(rec.frameIds[0]);
      if (first) {
        rec.fileNum = first.fileNum;
        rec.width = first.width;
        rec.height = first.height;
      }
    } else {
      rec.fileNum = readI32();
      rec.sx = readI16();
      rec.sy = readI16();
      rec.width = readI16();
      rec.height = readI16();
    }
    grhs.set(id, rec);
    if (id === count) break;
  }
  return { version, count, grhs, bytesRead: o, fileLength: b.length };
}

function writeString(value) {
  const body = Buffer.from(value, "latin1");
  const out = Buffer.alloc(2 + body.length);
  out.writeUInt16LE(body.length, 0);
  body.copy(out, 2);
  return out;
}

function writeMapDat(data) {
  return Buffer.concat([
    writeString(data.mapName),
    Buffer.from([data.backupMode]),
    writeString(data.restrictMode),
    i32(data.musicHi),
    i32(data.musicLow),
    Buffer.from([data.seguro]),
    writeString(data.zone),
    writeString(data.terrain),
    writeString(data.ambient),
    i32(data.baseLight),
    i32(data.letterGrh),
    i32(data.level),
    i32(data.extra2),
    writeString(data.salida),
    Buffer.from([data.lluvia, data.nieve, data.niebla]),
    // The server's t_MapDat (FileIO.bas) consumes exactly the fields above.
    // Writing trailing bytes here shifts every later block and breaks NPC/OBJ
    // loading server-side (fixed 2026-06-10, plan 10.003).
  ]);
}

function i16(value) {
  const b = Buffer.alloc(2);
  b.writeInt16LE(value, 0);
  return b;
}

function i32(value) {
  const b = Buffer.alloc(4);
  b.writeInt32LE(value, 0);
  return b;
}

function recordLayer(x, y, grh) {
  return Buffer.concat([i16(x), i16(y), i32(grh)]);
}

function recordObject(x, y, objIndex, amount) {
  return Buffer.concat([i16(x), i16(y), i16(objIndex), i16(amount)]);
}

function recordTrigger(x, y, trigger) {
  return Buffer.concat([i16(x), i16(y), i16(trigger)]);
}

function isWaterGrh(grh) {
  return WATER_GRHS.some(([lo, hi]) => grh >= lo && grh <= hi);
}

function parseMap(file) {
  const b = fs.readFileSync(file);
  let o = 0;
  const readI16 = () => {
    const v = b.readInt16LE(o);
    o += 2;
    return v;
  };
  const readI32 = () => {
    const v = b.readInt32LE(o);
    o += 4;
    return v;
  };
  const readU8 = () => b[o++];
  const readString = () => {
    const len = b.readUInt16LE(o);
    o += 2;
    const value = b.toString("latin1", o, o + len);
    o += len;
    return value;
  };

  const header = {
    blocked: readI32(),
    layer1: readI32(),
    layer2: readI32(),
    layer3: readI32(),
    layer4: readI32(),
    triggers: readI32(),
    lights: readI32(),
    particles: readI32(),
    npcs: readI32(),
    objects: readI32(),
    tileExits: readI32(),
  };
  const size = { xmax: readI16(), xmin: readI16(), ymax: readI16(), ymin: readI16() };
  const mapDat = {
    mapName: readString(),
    backupMode: readU8(),
    restrictMode: readString(),
    musicHi: readI32(),
    musicLow: readI32(),
    seguro: readU8(),
    zone: readString(),
    terrain: readString(),
    ambient: readString(),
    baseLight: readI32(),
    letterGrh: readI32(),
    level: readI32(),
    extra2: readI32(),
    salida: readString(),
    lluvia: readU8(),
    nieve: readU8(),
    niebla: readU8(),
  };
  // No trailing bytes: the server's t_MapDat ends at `niebla`. Official maps may
  // carry trailing data after tile exits, which the server (and we) ignore.

  const blocked = [];
  for (let i = 0; i < header.blocked; i++) {
    blocked.push({ x: readI16(), y: readI16(), sides: readU8() });
    o += 1;
  }
  const readLayers = (count) => {
    const rows = [];
    for (let i = 0; i < count; i++) rows.push({ x: readI16(), y: readI16(), grh: readI32() });
    return rows;
  };
  const layer1 = readLayers(header.layer1);
  const layer2 = readLayers(header.layer2);
  const layer3 = readLayers(header.layer3);
  const layer4 = readLayers(header.layer4);
  const triggers = [];
  for (let i = 0; i < header.triggers; i++) triggers.push({ x: readI16(), y: readI16(), trigger: readI16() });
  const particles = [];
  for (let i = 0; i < header.particles; i++) particles.push({ x: readI16(), y: readI16(), particle: readI32() });
  const lights = [];
  for (let i = 0; i < header.lights; i++) {
    lights.push({ x: readI16(), y: readI16(), color: readI32(), range: readU8() });
    o += 1;
  }
  const objects = [];
  for (let i = 0; i < header.objects; i++) objects.push({ x: readI16(), y: readI16(), objIndex: readI16(), amount: readI16() });
  const npcs = [];
  for (let i = 0; i < header.npcs; i++) npcs.push({ x: readI16(), y: readI16(), npcIndex: readI16() });
  const tileExits = [];
  for (let i = 0; i < header.tileExits; i++) tileExits.push({ x: readI16(), y: readI16(), destM: readI16(), destX: readI16(), destY: readI16() });

  return { header, size, mapDat, blocked, layer1, layer2, layer3, layer4, triggers, particles, lights, objects, npcs, tileExits, bytesRead: o, fileLength: b.length };
}

function validateCoord(x, y, label) {
  if (x < 1 || x > 100 || y < 1 || y > 100) throw new Error(`Invalid coord ${label}: ${x},${y}`);
}

function buildMap757() {
  const objects = parseObjects();
  const npcs = parseNpcs();
  const classified = classifyObjects(objects);
  const grh = parseGrhIndex(path.join(INIT, "graficos.ind"));

  const treeIds = classified.trees.filter((id) => [4, 5, 6, 31, 49, 50].includes(id));
  const requiredMinerals = [192, 193, 194, 3391, 3787];
  const deposits = requiredMinerals.map((mineral) => {
    const id = classified.oreDepositsByMineral.get(mineral);
    if (!id) throw new Error(`Missing ore deposit for mineral ${mineral} (${MINERALS.get(mineral)})`);
    return { mineral, id, label: MINERALS.get(mineral) };
  });

  const anvil = classified.anvils.includes(384) ? 384 : classified.anvils[0];
  const forge = classified.forges.includes(383) ? 383 : classified.forges[0];
  const fishingPool = classified.fishingPools.includes(3740) ? 3740 : classified.fishingPools[0];
  if (!anvil || !forge || !fishingPool || treeIds.length < 3) throw new Error("Missing required map objects");

  const layer1 = [];
  const water = new Set();
  for (let y = 1; y <= 100; y++) {
    for (let x = 1; x <= 100; x++) {
      let tile = 1;
      if (x >= 67 && x <= 92 && y >= 18 && y <= 46) {
        const dx = Math.min(x - 67, 92 - x);
        const dy = Math.min(y - 18, 46 - y);
        if (dx >= 0 && dy >= 0 && (dx > 1 || y % 2 === 0) && (dy > 1 || x % 2 === 0)) {
          tile = 1505 + ((x + y) % 16);
          water.add(`${x},${y}`);
        }
      }
      layer1.push({ x, y, grh: tile });
    }
  }

  const mapObjects = [];
  const addObj = (x, y, objIndex, amount = 1) => {
    validateCoord(x, y, `OBJ${objIndex}`);
    if (water.has(`${x},${y}`) && objIndex !== fishingPool) throw new Error(`Non-water object ${objIndex} on water ${x},${y}`);
    mapObjects.push({ x, y, objIndex, amount });
  };

  const treeLayout = [
    [24, 27], [29, 25], [34, 28], [25, 34], [31, 36], [38, 33],
    [23, 43], [30, 45], [37, 42], [44, 38], [45, 29], [40, 23],
  ];
  treeLayout.forEach(([x, y], i) => addObj(x, y, treeIds[i % treeIds.length], 1));

  const mineLayout = [
    [23, 69], [30, 70], [37, 69], [44, 70], [51, 69],
  ];
  deposits.forEach((d, i) => addObj(mineLayout[i][0], mineLayout[i][1], d.id, 1));

  addObj(26, 58, anvil, 1);
  addObj(30, 58, forge, 1);

  for (const [x, y] of [[74, 27], [82, 32], [88, 40]]) addObj(x, y, fishingPool, 1);

  const triggers = [];
  const header = [
    0,
    layer1.length,
    0,
    0,
    0,
    triggers.length,
    0,
    0,
    0,
    mapObjects.length,
    0,
  ];
  const mapDat = writeMapDat({
    mapName: "AO20 Lab Recursos",
    backupMode: 0,
    restrictMode: "0",
    musicHi: 0,
    musicLow: 0,
    seguro: 0,
    zone: "LAB",
    terrain: "BOSQUE",
    ambient: "",
    baseLight: 255,
    letterGrh: 0,
    level: 0,
    extra2: 0,
    salida: "",
    lluvia: 0,
    nieve: 0,
    niebla: 0,
  });

  const chunks = [];
  for (const n of header) chunks.push(i32(n));
  chunks.push(i16(0), i16(0), i16(0), i16(0));
  chunks.push(mapDat);
  for (const tile of layer1) chunks.push(recordLayer(tile.x, tile.y, tile.grh));
  for (const trigger of triggers) chunks.push(recordTrigger(trigger.x, trigger.y, trigger.trigger));
  for (const obj of mapObjects) chunks.push(recordObject(obj.x, obj.y, obj.objIndex, obj.amount));

  const out = Buffer.concat(chunks);
  const dst = path.join(MAPS, "mapa757.csm");
  fs.writeFileSync(dst, out);

  const parsed = validateMap(dst, { objects, npcs, grh: grh.grhs, expectMap: 757 });
  return {
    dst,
    bytes: out.length,
    objects: mapObjects,
    deposits,
    anvil,
    forge,
    fishingPool,
    waterTiles: parsed.waterTiles,
    waterPercent: parsed.waterPercent,
  };
}

function validateMap(file, catalogs = null) {
  const objects = catalogs?.objects ?? parseObjects();
  const npcs = catalogs?.npcs ?? parseNpcs();
  const grhIndex = catalogs?.grh ?? parseGrhIndex(path.join(INIT, "graficos.ind")).grhs;
  const parsed = parseMap(file);
  // Official maps may have trailing data after the server-consumed blocks.
  if (parsed.bytesRead > parsed.fileLength) throw new Error(`Parser consumed ${parsed.bytesRead}, file has ${parsed.fileLength}`);
  if (parsed.bytesRead < parsed.fileLength) console.warn(`(info) ${path.basename(file)}: ${parsed.fileLength - parsed.bytesRead} trailing bytes ignored`);

  const layers = [parsed.layer1, parsed.layer2, parsed.layer3, parsed.layer4];
  for (const [layerIndex, layer] of layers.entries()) {
    for (const tile of layer) {
      validateCoord(tile.x, tile.y, `L${layerIndex + 1}`);
      if (!grhIndex.has(tile.grh)) throw new Error(`Missing GRH ${tile.grh} at L${layerIndex + 1} ${tile.x},${tile.y}`);
    }
  }
  const seenObjects = new Set();
  for (const obj of parsed.objects) {
    validateCoord(obj.x, obj.y, `OBJ${obj.objIndex}`);
    if (seenObjects.has(`${obj.x},${obj.y}`)) throw new Error(`Duplicate object at ${obj.x},${obj.y}`);
    seenObjects.add(`${obj.x},${obj.y}`);
    if (!objects.has(obj.objIndex)) throw new Error(`Missing OBJ${obj.objIndex}`);
  }
  for (const npc of parsed.npcs) {
    validateCoord(npc.x, npc.y, `NPC${npc.npcIndex}`);
    if (!npcs.has(npc.npcIndex)) throw new Error(`Missing NPC${npc.npcIndex}`);
  }

  const waterTiles = parsed.layer1.filter((tile) => isWaterGrh(tile.grh)).length;
  const waterPercent = (waterTiles * 100) / parsed.layer1.length;
  const fishingPoolId = 3740;
  const hasFishingPool = parsed.objects.some((obj) => obj.objIndex === fishingPoolId);
  if (parsed.mapDat.seguro !== 0) throw new Error("Map must be non-safe for fishing pools");
  if (!hasFishingPool) throw new Error(`Map is missing explicit fishing pool OBJ${fishingPoolId}`);

  return { ...parsed, waterTiles, waterPercent };
}

function validateMapSequence() {
  const entries = fs.readdirSync(MAPS)
    .map((name) => {
      const m = /^mapa(\d+)\.csm$/i.exec(name);
      if (!m) return null;
      const id = Number(m[1]);
      const file = path.join(MAPS, name);
      return { id, name, length: fs.statSync(file).size };
    })
    .filter(Boolean)
    .sort((a, b) => a.id - b.id);

  const ids = new Set(entries.map((entry) => entry.id));
  const max = entries.length ? entries[entries.length - 1].id : 0;
  const gaps = [];
  for (let id = 1; id <= max; id++) {
    if (!ids.has(id)) gaps.push(id);
  }
  const zeroMap = entries.find((entry) => entry.id === 0);
  const rawCount = entries.length;
  // FileIO.CountFiles returns rawCount + 1, and LoadMapData subtracts 1.
  const normalMapsCount = rawCount;
  const missingLoadTargets = [];
  for (let id = 1; id <= normalMapsCount; id++) {
    if (!ids.has(id)) missingLoadTargets.push(id);
  }

  return { rawCount, max, zeroMap, gaps, normalMapsCount, missingLoadTargets };
}

function printSummary(summary) {
  console.log(JSON.stringify(summary, null, 2));
}

function main() {
  const cmd = process.argv[2];
  if (cmd === "generate-757") return printSummary(buildMap757());
  if (cmd === "validate") {
    const file = process.argv[3];
    if (!file) throw new Error("Usage: map_csm_tool.js validate <map.csm>");
    const parsed = validateMap(path.resolve(file));
    return printSummary({
      file: path.resolve(file),
      header: parsed.header,
      mapDat: parsed.mapDat,
      bytesRead: parsed.bytesRead,
      fileLength: parsed.fileLength,
      waterTiles: parsed.waterTiles,
      waterPercent: parsed.waterPercent,
      objects: parsed.objects,
      npcs: parsed.npcs,
    });
  }
  if (cmd === "catalog") {
    const objects = parseObjects();
    const classified = classifyObjects(objects);
    return printSummary({
      trees: classified.trees,
      oreDepositsByMineral: [...classified.oreDepositsByMineral].map(([mineral, id]) => ({ mineral, label: MINERALS.get(mineral), id })),
      anvils: classified.anvils,
      forges: classified.forges,
      fishingPools: classified.fishingPools,
    });
  }
  if (cmd === "sequence") return printSummary(validateMapSequence());
  throw new Error("Usage: map_csm_tool.js <catalog|generate-757|validate>");
}

try {
  main();
} catch (err) {
  console.error(err.stack || err.message);
  process.exit(1);
}
