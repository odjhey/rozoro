import assert from "node:assert/strict";
import { chmod, mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { createServer } from "node:net";
import test from "node:test";
import extension from "../.pi/extensions/rozoro-watchtower.ts";
import { RozoroEventBusClient } from "../.pi/lib/rozoro-event-bus-client.ts";

const wait=async(f:()=>boolean)=>{for(let i=0;i<200;i++){if(f())return;await new Promise(r=>setTimeout(r,10));}throw new Error("timeout")};

test("Pi extension entrypoint honors relative legacy home once across cwd change", {concurrency:false}, async()=>{
 const root=await mkdtemp(join(tmpdir(),"rzr-pi-home-")); const initial=join(root,"initial"), later=join(root,"later"), selected=join(initial,"legacy");
 await Promise.all([import("node:fs/promises").then(fs=>fs.mkdir(initial)),import("node:fs/promises").then(fs=>fs.mkdir(later)),import("node:fs/promises").then(fs=>fs.mkdir(selected))]); await chmod(selected,0o700);
 const socket=join(selected,"monitor.sock"); let connected=false;
 const server=createServer(s=>{connected=true;s.on("error",()=>{});s.on("data",()=>{});}); await new Promise<void>(r=>server.listen(socket,r)); await chmod(socket,0o600);
 const old={cwd:process.cwd(),public:process.env.ROZORO_HOME,legacy:process.env.RZR_HOME}; process.chdir(initial); delete process.env.ROZORO_HOME; process.env.RZR_HOME="legacy";
 const handlers=new Map<string,Function[]>(); const pi:any={on:(n:string,f:Function)=>handlers.set(n,[...(handlers.get(n)??[]),f]),registerCommand(){},sendMessage(){},exec:async()=>({code:0,stdout:"",stderr:""})};
 extension(pi); process.chdir(later);
 const ctx:any={getSystemPrompt:()=>"rozoro-task: task-1",sessionManager:{getSessionId:()=>"s"},ui:{setStatus(){},notify(){}}};
 for(const fn of handlers.get("session_start")??[]) await fn({},ctx); await wait(()=>connected);
 for(const fn of handlers.get("session_shutdown")??[]) await fn(); server.close(); process.chdir(old.cwd); if(old.public===undefined)delete process.env.ROZORO_HOME;else process.env.ROZORO_HOME=old.public;if(old.legacy===undefined)delete process.env.RZR_HOME;else process.env.RZR_HOME=old.legacy; await rm(root,{recursive:true,force:true});
});

test("Pi readiness waits for persistent authority activation", async()=>{
 const home=await mkdtemp(join(tmpdir(),"rzr-pi-authority-")); await chmod(home,0o700); const path=join(home,"monitor.sock"); const seen:string[]=[];
 const server=createServer(s=>{s.on("error",()=>{});let b="";s.on("data",c=>{b+=c;const i=b.indexOf("\n");if(i>=0){const f=JSON.parse(b.slice(0,i));seen.push(f.type);s.write(JSON.stringify({v:1,type:"ok",request_id:f.request_id})+"\n")}})}); await new Promise<void>(r=>server.listen(path,r)); await chmod(path,0o600);
 const states:string[]=[]; const client=new RozoroEventBusClient({socketPath:path,sessionId:"s",driverId:"d",onNotification:()=>{},onRegistered:async()=>{await new Promise(r=>setTimeout(r,40));seen.push("authority-marker")},onStatus:s=>states.push(s),pollMs:10000}); client.start();
 await wait(()=>states.some(s=>s.includes("authority active"))); assert.deepEqual(seen.slice(0,2),["watchtower.register","authority-marker"]); client.close(); server.close(); await rm(home,{recursive:true,force:true});
});

test("managed Pi crew publishes task-scoped lifecycle without watchtower registration", async()=>{
 const home=await mkdtemp(join(tmpdir(),"rzr-pi-crew-")); await chmod(home,0o700); const path=join(home,"monitor.sock"); const frames:any[]=[];
 const server=createServer(s=>{let b="";s.on("data",c=>{b+=c;for(;;){const i=b.indexOf("\n");if(i<0)break;const f=JSON.parse(b.slice(0,i));b=b.slice(i+1);frames.push(f);s.write(JSON.stringify({v:1,type:"ack",event_id:f.event_id,durable_seq:frames.length})+"\n")}})}); await new Promise<void>(r=>server.listen(path,r)); await chmod(path,0o600);
 const client=new RozoroEventBusClient({socketPath:path,sessionId:"s",role:"crew",taskId:"task-1"}); client.start(); client.publish("turn.start"); client.publish("turn.stop"); await wait(()=>frames.length===3);
 assert.deepEqual(frames.map(f=>f.type),["session.register","turn.start","turn.stop"]); assert.ok(frames.every(f=>f.role==="crew"&&f.task_id==="task-1"&&!f.driver_id)); client.close(); server.close(); await rm(home,{recursive:true,force:true});
});
