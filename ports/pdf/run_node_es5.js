// Run an ES5 harness inside a fresh node vm context from which every post-ES5 convenience the
// engine could accidentally lean on has been deleted (BigInt, TextEncoder, normalize, Map, ...).
// usage: node ports/pdf/run_node_es5.js HARNESS.js
const vm = require("vm"), fs = require("fs");
const ctx = vm.createContext({ print: (s) => console.log(s) });
vm.runInContext(`
  delete this.BigInt; delete this.BigInt64Array; delete this.BigUint64Array;
  delete this.TextEncoder; delete this.TextDecoder; delete this.DecompressionStream; delete this.Intl;
  delete String.prototype.normalize; delete String.prototype.codePointAt; delete String.fromCodePoint;
  delete String.prototype.startsWith; delete String.prototype.includes; delete String.prototype.repeat;
  delete String.prototype.padStart; delete String.prototype.matchAll;
  delete Array.from; delete Array.prototype.includes; delete Array.prototype.find; delete Array.prototype.findIndex;
  delete Object.assign; delete Math.imul; delete Math.clz32;
  ["Map","Set","WeakMap","WeakSet","Symbol","Promise","Proxy","Reflect","ArrayBuffer","DataView","Uint8Array",
   "Int8Array","Uint16Array","Int16Array","Uint32Array","Int32Array","Float32Array","Float64Array","Uint8ClampedArray"]
   .forEach(function (n) { delete this[n]; }, this);
`, ctx);
const missing = vm.runInContext("[typeof BigInt, typeof TextEncoder, typeof ''.normalize, typeof Map, typeof Uint8Array].join(',')", ctx);
console.log("node vm (ES5-stripped): BigInt,TextEncoder,normalize,Map,Uint8Array =", missing);
vm.runInContext(fs.readFileSync(process.argv[2], "utf8"), ctx, { filename: process.argv[2] });
