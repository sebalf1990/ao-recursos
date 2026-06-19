#!/usr/bin/env node
"use strict";
// Plan 18.002: coloca un lote de OBJs y NPCs en Mapa755.csm para validacion in-game.
// Reescribe SOLO los bloques de objetos y npcs + sus contadores en el header.
// El resto del .csm queda byte-identico. Formato segun map_csm_tool.js / place_objs_755.js.
// OBJs: grilla desde (50,50), 5/fila, paso 2.  NPCs: grilla desde (50,56), 5/fila, paso 2.
// Uso: node place_test_755.js objs=463,1089,... npcs=689,1349,...   (cualquiera puede faltar)
//      node place_test_755.js clean   -> vacia ambos bloques

const fs = require("fs");
const MAP = "C:/AO20/dev/Recursos/Mapas/Mapa755.csm";
const b = fs.readFileSync(MAP);
let o = 0;
const rI32 = () => { const v = b.readInt32LE(o); o += 4; return v; };
const rI16 = () => { const v = b.readInt16LE(o); o += 2; return v; };
const rU8 = () => b[o++];
const rStr = () => { const len = b.readUInt16LE(o); o += 2; o += len; };

const H = {
  blocked: rI32(), layer1: rI32(), layer2: rI32(), layer3: rI32(), layer4: rI32(),
  triggers: rI32(), lights: rI32(), particles: rI32(), npcs: rI32(), objects: rI32(), tileExits: rI32(),
};
rI16(); rI16(); rI16(); rI16();                 // size
rStr(); rU8(); rStr(); rI32(); rI32(); rU8();   // mapDat name,backup,restrict,musicHi,musicLow,seguro
rStr(); rStr(); rStr(); rI32(); rI32(); rI32(); rI32(); // zone,terrain,ambient,baseLight,letterGrh,level,extra2
rStr(); rU8(); rU8(); rU8();                     // salida,lluvia,nieve,niebla
for (let i = 0; i < H.blocked; i++) o += 6;
for (let i = 0; i < H.layer1 + H.layer2 + H.layer3 + H.layer4; i++) o += 8;
for (let i = 0; i < H.triggers; i++) o += 6;
for (let i = 0; i < H.particles; i++) o += 8;
for (let i = 0; i < H.lights; i++) o += 10;
const objStart = o;
const objEnd = objStart + H.objects * 8;
const npcStart = objEnd;
const npcEnd = npcStart + H.npcs * 6;

// args
const args = process.argv.slice(2).join(" ");
const clean = /\bclean\b/.test(args);
const grab = (k) => { const m = new RegExp(k + "=([0-9,]+)").exec(args); return m ? m[1].split(",").map(Number).filter(Boolean) : []; };
const objIds = clean ? [] : grab("objs");
const npcIds = clean ? [] : grab("npcs");
if (!clean && !objIds.length && !npcIds.length) { console.error("uso: place_test_755.js objs=.. npcs=.. | clean"); process.exit(1); }
if (objIds.length > 10 || npcIds.length > 10) { console.error("max 10 por bloque"); process.exit(1); }

const grid = (arr, y0) => arr.map((id, i) => ({ x: 50 + (i % 5) * 2, y: y0 + Math.floor(i / 5) * 2, id }));
const objs = grid(objIds, 50);
const npcs = grid(npcIds, 56);
for (const p of [...objs, ...npcs]) if (p.x < 1 || p.x > 100 || p.y < 1 || p.y > 100) { console.error("coord fuera de rango", p); process.exit(1); }

const objBuf = Buffer.alloc(objs.length * 8);
let q = 0;
for (const ob of objs) { objBuf.writeInt16LE(ob.x, q); objBuf.writeInt16LE(ob.y, q + 2); objBuf.writeInt16LE(ob.id, q + 4); objBuf.writeInt16LE(1, q + 6); q += 8; }
const npcBuf = Buffer.alloc(npcs.length * 6);
q = 0;
for (const np of npcs) { npcBuf.writeInt16LE(np.x, q); npcBuf.writeInt16LE(np.y, q + 2); npcBuf.writeInt16LE(np.id, q + 4); q += 6; }

const head = Buffer.from(b.slice(0, 44)); // copia mutable de los 11 contadores
head.writeInt32LE(npcs.length, 32);       // npcs count
head.writeInt32LE(objs.length, 36);       // objects count

const out = Buffer.concat([
  head,                       // header (44 bytes) con contadores npcs/objects actualizados
  b.slice(44, objStart),      // size + mapDat + blocked..lights (byte-identico)
  objBuf,                     // nuevo bloque objetos
  npcBuf,                     // nuevo bloque npcs
  b.slice(npcEnd),            // tileExits + trailing (byte-identico)
]);
fs.writeFileSync(MAP, out);
console.log(`objetos ${H.objects}->${objs.length}  npcs ${H.npcs}->${npcs.length}  bytes ${b.length}->${out.length}`);
console.log("OBJ:", objs.map(p => `${p.id}@(${p.x},${p.y})`).join(" "));
console.log("NPC:", npcs.map(p => `${p.id}@(${p.x},${p.y})`).join(" "));

// re-parse verificacion de contadores
const v = fs.readFileSync(MAP);
console.log(`verif header: npcs=${v.readInt32LE(32)} objects=${v.readInt32LE(36)}`);
