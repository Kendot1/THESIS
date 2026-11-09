import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
import { createRequire } from 'node:module';
const native = createRequire(import.meta.url);
export function loadTs(file, deps = {}) {
 const module = {exports:{}};
 const path = new URL(file, import.meta.url);
 const require = id => id in deps ? deps[id] : id.startsWith('.') ? loadTs(new URL(id.endsWith('.ts') ? id : `${id}.ts`, path).href) : id === 'server-only' ? {} : native(id);
 vm.runInNewContext(ts.transpileModule(fs.readFileSync(path,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020,jsx:ts.JsxEmit.ReactJSX,esModuleInterop:true}}).outputText,{module,exports:module.exports,require,process,Buffer,Date,Map,Set,Number,Math,JSON,URL,URLSearchParams,Request,Response});
 return module.exports;
}
