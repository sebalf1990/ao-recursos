#!/usr/bin/env node
"use strict";
// Plan 16.001 Fase 2: coloca un lote de OBJs en Mapa755.csm para validacion in-game.
// Splice quirurgico: solo reescribe el bloque de objetos + el contador del header.
// El resto del .csm (header, size, mapDat, layers, triggers, particles, lights, npcs,
// tileExits, trailing) queda byte-identico. Formato segun map_csm_tool.js.
// Uso: node place_objs_755.js 1715,1719,1273,...

const fs = require("fs");
const MAP = "C:/AO20/dev/Recursos/Mapas/Mapa755.csm";

const b = fs.readFileSync(MAP);
let o = 0;
const rI16 = () => { const v = b.readInt16LE(o); o += 2; return v; };
const rI32 = () => { const v = b.readInt32LE(o); o += 4; return v; };
const rU8 = () => b[o++];
const rStr = () => { const len = b.readUInt16LE(o); o += 2; o += len; };

const H = {
  blocked: rI32(), layer1: rI32(), layer2: rI32(), layer3: rI32(), layer4: rI32(),
  triggers: rI32(), lights: rI32(), particles: rI32(), npcs: rI32(), objects: rI32(), tileExits: rI32(),
};
rI16(); rI16(); rI16(); rI16();                 // size
rStr(); rU8(); rStr(); rI32(); rI32(); rU8();   // mapDat: name,backup,restrict,musicHi,musicLow,seguro
rStr(); rStr(); rStr(); rI32(); rI32(); rI32(); rI32(); // zone,terrain,ambient,baseLight,letterGrh,level,extra2
rStr(); rU8(); rU8(); rU8();                     // salida,lluvia,nieve,niebla
for (let i = 0; i < H.blocked; i++) { o += 2 + 2 + 1; o += 1; }
for (let i = 0; i < H.layer1 + H.layer2 + H.layer3 + H.layer4; i++) o += 8;
for (let i = 0; i < H.triggers; i++) o += 6;
for (let i = 0; i < H.particles; i++) o += 8;
for (let i = 0; i < H.lights; i++) { o += 2 + 2 + 4 + 1; o += 1; }
const objStart = o;
const objEnd = objStart + H.objects * 8;

// lote desde argv ("clean" = vaciar el mapa)
const arg = (process.argv[2] || "").trim();
const batch = arg === "clean" ? [] : arg.split(",").map(s => Number(s.trim())).filter(Boolean);
if (arg !== "clean" && !batch.length) { console.error("dame ids: node place_objs_755.js 1715,1719,... | clean"); process.exit(1); }
if (batch.length > 10) { console.error("max 10 por lote"); process.exit(1); }

// grilla agrupada alrededor de (50,50): 5 por fila, paso 2 (1 tile de separacion en x e y).
// El script SIEMPRE limpia el mapa (reemplaza todos los objetos) y recoloca solo el lote.
const COLS = 5;
const placed = batch.map((id, i) => ({ x: 50 + (i % COLS) * 2, y: 50 + Math.floor(i / COLS) * 2, id, amount: 1 }));
for (const p of placed) if (p.x < 1 || p.x > 100) { console.error("coord fuera de rango", p); process.exit(1); }

const objBuf = Buffer.alloc(placed.length * 8);
let p = 0;
for (const ob of placed) {
  objBuf.writeInt16LE(ob.x, p); objBuf.writeInt16LE(ob.y, p + 2);
  objBuf.writeInt16LE(ob.id, p + 4); objBuf.writeInt16LE(ob.amount, p + 6); p += 8;
}
const cnt = Buffer.alloc(4); cnt.writeInt32LE(placed.length, 0);

const out = Buffer.concat([
  b.slice(0, 36),      // header fields 0..8 (blocked..npcs)
  cnt,                 // header[9] = objects count (offset 36)
  b.slice(40, objStart), // header[10] tileExits + size + mapDat + blocked..lights
  objBuf,              // nuevo bloque de objetos
  b.slice(objEnd),     // npcs + tileExits + trailing
]);
fs.writeFileSync(MAP, out);

console.log(`objetos previos=${H.objects} -> nuevos=${placed.length}`);
console.log(`bytes ${b.length} -> ${out.length} (delta ${out.length - b.length})`);
console.log("colocados:", placed.map(p => `OBJ${p.id}@(${p.x},${p.y})`).join("  "));

// re-parse de verificacion
let o2 = 36; const newCnt = out.readInt32LE(o2);
console.log(`verif: header.objects=${newCnt} (esperado ${placed.length})`);
let vo = objStart; const got = [];
for (let i = 0; i < newCnt; i++) { const x = out.readInt16LE(vo); const y = out.readInt16LE(vo + 2); const id = out.readInt16LE(vo + 4); vo += 8; got.push(`OBJ${id}@(${x},${y})`); }
console.log("releido:", got.join("  "));
