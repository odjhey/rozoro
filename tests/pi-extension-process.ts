import { readFile } from "node:fs/promises";
import { spawn } from "node:child_process";
import extension from "../.pi/extensions/rozoro-watchtower.ts";

const [sysfile, sessionId] = process.argv.slice(2);
if (!sysfile || !sessionId) throw new Error("usage: pi-extension-process.ts SYSFILE SESSION");
const handlers = new Map<string, Function[]>();
const api:any = {
  on(name:string, fn:Function) { const xs=handlers.get(name)??[]; xs.push(fn); handlers.set(name,xs); },
  registerCommand() {}, sendMessage() {},
  exec(command:string,args:string[]) { return new Promise(resolve=>{const p=spawn(command,args,{env:process.env});let stdout="",stderr="";p.stdout.on("data",x=>stdout+=x);p.stderr.on("data",x=>stderr+=x);p.on("close",code=>resolve({code:code??1,stdout,stderr}));}); },
};
extension(api);
const prompt=await readFile(sysfile,"utf8");
const ctx:any={getSystemPrompt:()=>prompt,sessionManager:{getSessionId:()=>sessionId},ui:{setStatus(){},notify(){}}};
const emit=async(name:string,...args:any[])=>{for(const fn of handlers.get(name)??[]) await fn(...args)};
await emit("session_start",{},ctx); await new Promise(r=>setTimeout(r,400));
await emit("agent_start"); await emit("agent_settled"); await new Promise(r=>setTimeout(r,400));
await emit("session_shutdown");
