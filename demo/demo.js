"use strict";
/* ============================================================================
   Canonical tables — MIRRORS of the app's single sources of truth.
   (serial.js: BTN:/ENC: -> action) and (terminal.py: action -> key bytes)
============================================================================ */
const BUTTON_ACTIONS  = { "0":"yes", "1":"no", "2":"stop", "8":"confirm" };
const ENCODER_ACTIONS = { CW:"nav_down", VDN:"nav_down", CCW:"nav_up", VUP:"nav_up" };
const ACTION_KEYS = {                 // action -> literal key sequence sent to Claude's PTY
  nav_up:"\x1b[A", nav_down:"\x1b[B", confirm:"\r", yes:"\r", no:"\x1b", stop:"\x1b",
};
const KEY_GLYPH = { "\r":"⏎ (\\r)", "\x1b":"⎋ (\\x1b)", "\x1b[A":"↑ (\\x1b[A)", "\x1b[B":"↓ (\\x1b[B)" };
const ACTION_LABEL = { yes:"YES", no:"NO", stop:"STOP", confirm:"ENTER", nav_up:"▲ UP", nav_down:"▼ DOWN" };

// Pure mapping — mirror of serial.js parseDeviceLine (total; unknown -> null).
function parseDeviceLine(line){
  if (typeof line !== "string") return null;
  const b = /^BTN:([0-8])$/.exec(line);   if (b) return BUTTON_ACTIONS[b[1]] || null;
  const e = /^ENC:([A-Z]+)$/.exec(line);  if (e) return ENCODER_ACTIONS[e[1]] || null;
  return null;
}

/* ============================================================================
   Scripted Claude session.  Events run in order; a "prompt" pauses for input.
============================================================================ */
const SCRIPT = [
  { t:"say", cls:"u",   text:"› /health 엔드포인트를 추가하고 테스트를 돌려줘. 이상 없으면 커밋까지." },
  { t:"say", cls:"sys", text:"● 좋아요. server.py에 /health를 추가하고 테스트를 실행할게요." },
  { t:"gate",
    tool:"Edit", target:"server.py",
    summary:"server.py 에 GET /health 핸들러 추가",
    options:[
      { label:"Yes", approve:true },
      { label:"Yes, and don't ask again for Edit in this session", approve:true },
      { label:"No, tell Claude what to do differently", approve:false },
    ],
    approveSay:[
      { cls:"ok",  text:"✔ server.py 수정 완료 — /health 핸들러 추가" },
      { cls:"sys", text:"● 이제 테스트를 실행해 볼게요." },
    ],
    denySay:[
      { cls:"warn", text:"↩ 편집을 취소했어요. 어떻게 바꿀지 알려주면 다시 시도할게요." },
      { cls:"sys",  text:"● (데모) 그래도 다음 단계로 진행합니다 — 테스트 실행 제안." },
    ],
  },
  { t:"gate",
    tool:"Bash", target:"npm test",
    summary:"테스트 스위트 실행: npm test",
    options:[
      { label:"Yes", approve:true },
      { label:"Yes, and don't ask again for Bash in this session", approve:true },
      { label:"No, tell Claude what to do differently", approve:false },
    ],
    approveSay:[
      { cls:"dim", text:"$ npm test" },
      { cls:"ok",  text:"✔ 43 passing (31 python + 12 js)" },
      { cls:"sys", text:"● 통과했어요. 변경을 커밋하고 푸시할까요?" },
    ],
    denySay:[
      { cls:"warn", text:"↩ 테스트 실행을 건너뜁니다." },
      { cls:"sys",  text:"● 변경을 커밋하고 푸시할까요?" },
    ],
  },
  { t:"gate",
    tool:"Bash", target:"git push origin main",
    summary:"원격 저장소로 푸시: git push origin main",
    danger:true,
    options:[
      { label:"Yes", approve:true },
      { label:"Yes, and don't ask again for Bash in this session", approve:true },
      { label:"No, tell Claude what to do differently", approve:false },
    ],
    approveSay:[
      { cls:"dim", text:"$ git push origin main" },
      { cls:"ok",  text:"✔ pushed. (데모 시나리오 종료)" },
    ],
    denySay:[
      { cls:"warn", text:"↩ 푸시를 거절했습니다 — 원격은 그대로예요." },
      { cls:"sys",  text:"● 알겠어요. 로컬 변경만 남겨둘게요. (데모 시나리오 종료)" },
    ],
  },
  { t:"done" },
];

/* ============================================================================
   State + rendering
============================================================================ */
const S = {
  queue:[], claudeState:"idle", lastAnswer:"—",
  gate:null,      // active prompt object {tool,target,options,menuIndex,...}
  transcript:[],  // rendered lines
  signals:0, autoplay:false, autoTimer:null, finished:false,
};

const $ = (id)=>document.getElementById(id);
const term=$("terminal"), stateBadge=$("state-badge"), stepLabel=$("step-label");
const oledState=$("oled-state"), oledLast=$("oled-last"), oledPrompt=$("oled-prompt"), oledEl=$("oled");
const serialLog=$("serial-log"), signalCount=$("signal-count"), knobTick=$("knob-tick");
let knobDeg=0;

function setState(s){
  S.claudeState=s;
  stateBadge.className="badge "+s;
  stateBadge.textContent = {idle:"대기",active:"실행 중",waiting:"승인 대기"}[s]||s;
  renderOLED(); renderDeviceEnabled();
}
function renderOLED(){
  oledState.textContent=S.claudeState;
  oledLast.textContent=S.lastAnswer;
  oledEl.classList.toggle("blank", S.claudeState==="idle");
  if (S.gate){
    const o=S.gate.options[S.gate.menuIndex];
    oledPrompt.textContent="▶ "+S.gate.tool+": "+S.gate.target;
  } else if (S.finished){
    oledPrompt.textContent="세션 종료 · 다시 시작 가능";
  } else if (S.claudeState==="active"){
    oledPrompt.textContent="Claude 작업 중…";
  } else {
    oledPrompt.textContent="Claude 시작을 기다리는 중…";
  }
}
function renderTerminal(){
  let html="";
  for (const l of S.transcript) html += `<div class="${l.cls||''}">${escapeHtml(l.text)}</div>`;
  if (S.gate){
    const g=S.gate;
    html += `<div class="permit"><div class="p-head">Claude가 <span class="p-tool">${escapeHtml(g.tool)}</span> 실행 권한을 요청합니다 — <b>${escapeHtml(g.target)}</b><div class="dim" style="margin-top:3px">${escapeHtml(g.summary)}</div></div>`;
    g.options.forEach((o,i)=>{
      const sel = i===g.menuIndex;
      const cls = "opt "+(o.approve?"approve":"decline")+(sel?" sel":"");
      html += `<div class="${cls}"><span class="marker">${sel?"❯":" "}</span><span>${i+1}. ${escapeHtml(o.label)}</span></div>`;
    });
    html += `<div class="p-foot">엔코더 ▲/▼ 로 이동 · YES/ENTER 로 선택 확정 · NO/STOP 으로 거절</div></div>`;
  } else if (!S.finished && S.claudeState==="active"){
    html += `<div><span class="cursor"></span></div>`;
  }
  term.innerHTML=html;
  term.scrollTop=term.scrollHeight;
}
function renderDeviceEnabled(){
  const waiting = S.claudeState==="waiting";
  // yes/no/nav/confirm meaningful only while waiting; stop always allowed when a session is live.
  document.querySelectorAll('.key.mapped').forEach(k=>{
    const action=parseDeviceLine(k.dataset.line);
    const on = action==="stop" ? (S.claudeState!=="idle") : waiting;
    k.disabled=!on; k.classList.toggle("inert",!on);
  });
  document.querySelectorAll('.enc-btns button').forEach(b=>{ b.disabled=!waiting; });
  $("knob").style.opacity = waiting? "1":".5";
}
function escapeHtml(s){return String(s).replace(/[&<>]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;"}[c]));}

/* ---- serial monitor ---- */
function log(src, text, cls){
  const now=new Date();
  const t=`${String(now.getHours()).padStart(2,"0")}:${String(now.getMinutes()).padStart(2,"0")}:${String(now.getSeconds()).padStart(2,"0")}`;
  const row=document.createElement("div");
  row.className="log-line "+(cls||"info");
  row.innerHTML=`<span class="log-time">${t}</span><span class="log-src">${escapeHtml(src)}</span><span class="log-text">${escapeHtml(text)}</span>`;
  serialLog.appendChild(row); serialLog.scrollTop=serialLog.scrollHeight;
}

/* ============================================================================
   Scenario engine
============================================================================ */
function restart(){
  clearTimeout(S.autoTimer); S.autoplay=false; $("btn-autoplay").textContent="▶ 자동 재생";
  S.queue = SCRIPT.slice();
  S.transcript=[]; S.gate=null; S.finished=false; S.lastAnswer="—";
  setState("active"); renderTerminal();
  stepLabel.textContent="세션 시작됨"; log("claude","세션 시작 (재현)","info");
  runNext();
}
function runNext(){
  const ev=S.queue.shift();
  if(!ev){ return; }
  if(ev.t==="say"){
    S.transcript.push({cls:ev.cls,text:ev.text}); renderTerminal();
    scheduleContinue(()=>runNext());
  } else if(ev.t==="gate"){
    S.gate={...ev, menuIndex:0};
    setState("waiting"); renderTerminal(); renderOLED();
    stepLabel.textContent="승인 대기: "+ev.tool+" · "+ev.target;
    log("claude","승인 프롬프트: "+ev.tool+" ("+ev.target+")","info");
    if(S.autoplay) scheduleAuto();
  } else if(ev.t==="done"){
    S.finished=true; S.gate=null;
    S.transcript.push({cls:"sys",text:"● 완료. '시나리오 다시 시작'으로 다시 재생할 수 있어요."});
    stepLabel.textContent="완료";
    S.autoplay=false; $("btn-autoplay").textContent="▶ 자동 재생"; clearTimeout(S.autoTimer);
    setState("idle");   // one clean transition: badge/OLED/device all consistent
    renderTerminal();
  }
}
function scheduleContinue(fn){
  if(S.autoplay){ S.autoTimer=setTimeout(fn, 620); }
  else { S.autoTimer=setTimeout(fn, 260); }
}

function resolveGate(approved, viaLabel){
  const g=S.gate; if(!g) return;
  const chosen = g.options[g.menuIndex];
  S.lastAnswer = approved ? "YES" : "NO";
  const branch = approved ? g.approveSay : g.denySay;
  log("claude", (approved?"승인":"거절")+" → "+g.tool+" ("+g.target+")", approved?"yes":"no");
  S.gate=null; setState("active"); renderTerminal();
  // splice branch lines to the front as say-events
  const says = branch.map(b=>({t:"say",cls:b.cls,text:b.text}));
  S.queue = says.concat(S.queue);
  scheduleContinue(()=>runNext());
}

/* ============================================================================
   Input handling — the heart of the demo
   device line -> parseDeviceLine -> action -> ACTION_KEYS[action] -> effect
============================================================================ */
function feedLine(rawLine, src){
  const line=String(rawLine).trim();
  const action=parseDeviceLine(line);
  if(!action){ log(src||"serial", line+"  → (무시됨, 매핑 없음)","info"); return; }
  applyAction(action, line, src||"serial");
}
function applyAction(action, line, src){
  const keys=ACTION_KEYS[action];
  const glyph=KEY_GLYPH[keys]||JSON.stringify(keys);
  // Gate readiness (mirrors the real host: prompt-actions need waiting; stop needs a live session)
  const isStop = action==="stop";
  const ready = isStop ? (S.claudeState!=="idle") : (S.claudeState==="waiting");
  const cls = action==="yes"?"yes":action==="no"?"no":(action==="nav_up"||action==="nav_down")?"nav":"info";
  const chain = (line?line+" → ":"") + action + " → " + glyph;
  if(!ready){
    log(src, chain+"   ✗ (지금은 전송 불가: "+ (isStop?"세션이 없음":"승인 대기 아님") +")","info");
    return;
  }
  S.signals++; signalCount.textContent=S.signals;
  log(src, chain, cls);
  bumpSignalToOLED();

  const g=S.gate;
  if(action==="nav_up"){ if(g){ g.menuIndex=Math.max(0,g.menuIndex-1); renderTerminal(); renderOLED(); } spinKnob(-1); }
  else if(action==="nav_down"){ if(g){ g.menuIndex=Math.min(g.options.length-1,g.menuIndex+1); renderTerminal(); renderOLED(); } spinKnob(1); }
  else if(action==="confirm"||action==="yes"){
    // Enter/\r selects the CURRENTLY highlighted option.
    if(g){ const opt=g.options[g.menuIndex]; resolveGate(!!opt.approve, opt.label); }
  }
  else if(action==="no"){ if(g){ resolveGate(false,"(Esc)"); } }
  else if(action==="stop"){
    if(g){ resolveGate(false,"(Esc/STOP)"); }
    else { log("claude","STOP → 현재 작업 중단(Esc)","no"); }
  }
}
function bumpSignalToOLED(){ renderOLED(); }
function spinKnob(dir){ knobDeg += dir*40; knobTick.style.transform=`rotate(${knobDeg}deg)`; }

/* pulse a key visually */
function pulseKey(el){ if(!el) return; el.classList.add("pressed"); setTimeout(()=>el.classList.remove("pressed"),140); }

/* ---- autoplay: pick the "interesting" answer automatically ---- */
function scheduleAuto(){
  if(!S.autoplay||!S.gate) return;
  const g=S.gate;
  // Demo choice: approve the first two gates; decline the dangerous push (nav to "No" then confirm).
  const wantDeny = !!g.danger;
  const targetIndex = wantDeny ? g.options.length-1 : 0;
  const stepAuto=()=>{
    if(!S.autoplay||!S.gate) return;
    if(S.gate.menuIndex<targetIndex){ triggerLine("ENC:CW","auto"); S.autoTimer=setTimeout(stepAuto,520); }
    else if(S.gate.menuIndex>targetIndex){ triggerLine("ENC:CCW","auto"); S.autoTimer=setTimeout(stepAuto,520); }
    else {
      if(wantDeny) triggerLine("BTN:1","auto");   // NO
      else         triggerLine("BTN:0","auto");   // YES
    }
  };
  S.autoTimer=setTimeout(stepAuto,700);
}
function triggerLine(line,src){
  const el=document.querySelector(`[data-line="${line}"]`); pulseKey(el&&el.classList.contains("key")?el:null);
  feedLine(line,src);
}

/* ============================================================================
   Wiring
============================================================================ */
document.querySelectorAll('.key.mapped, .enc-btns button').forEach(el=>{
  el.addEventListener("click",()=>{ if(el.disabled) return; pulseKey(el.classList.contains("key")?el:null); feedLine(el.dataset.line,"hardware"); });
});
$("knob").addEventListener("click",()=>feedLine("BTN:8","hardware"));         // encoder push -> confirm
$("knob").addEventListener("keydown",e=>{ if(e.key==="Enter"||e.key===" "){ e.preventDefault(); feedLine("BTN:8","hardware"); }});
$("btn-restart").addEventListener("click",restart);
$("btn-autoplay").addEventListener("click",()=>{
  S.autoplay=!S.autoplay;
  $("btn-autoplay").textContent = S.autoplay ? "⏸ 자동 재생 중" : "▶ 자동 재생";
  if(S.autoplay){
    if(S.finished||S.claudeState==="idle") restart();
    if(S.gate) scheduleAuto();
  } else { clearTimeout(S.autoTimer); }
});
$("feeder-send").addEventListener("click",()=>{ const v=$("feeder-input").value; if(v.trim()){ feedLine(v,"serial-in"); $("feeder-input").value=""; }});
$("feeder-input").addEventListener("keydown",e=>{ if(e.key==="Enter"){ $("feeder-send").click(); }});

// keyboard shortcuts (mirror app.js)
const KEYMAP={ y:"BTN:0", n:"BTN:1", arrowup:"ENC:CCW", arrowdown:"ENC:CW", enter:"BTN:8", escape:"BTN:2" };
document.addEventListener("keydown",e=>{
  if(e.target.tagName==="INPUT") return;
  const line=KEYMAP[e.key.toLowerCase()];
  if(line){ e.preventDefault(); const el=document.querySelector(`[data-line="${line}"]`); pulseKey(el&&el.classList.contains("key")?el:null); feedLine(line,"keyboard"); }
});

/* legend table */
(function fillLegend(){
  const rows=[
    ["BTN:0 (YES 키)","BTN:0","yes","\r","현재 선택 항목 확정(승인)"],
    ["BTN:1 (NO 키)","BTN:1","no","\x1b","프롬프트 거절"],
    ["BTN:2 (STOP 키)","BTN:2","stop","\x1b","실행 중 작업 중단"],
    ["엔코더 누름","BTN:8","confirm","\r","선택 항목 확정"],
    ["엔코더 CW ⟳","ENC:CW","nav_down","\x1b[B","메뉴 아래로"],
    ["엔코더 CCW ⟲","ENC:CCW","nav_up","\x1b[A","메뉴 위로"],
  ];
  $("legend-body").innerHTML=rows.map(r=>
    `<tr><td>${escapeHtml(r[0])}</td><td>${escapeHtml(r[1])}</td><td class="kmap">${escapeHtml(r[2])}</td><td class="kmap">${escapeHtml(KEY_GLYPH[r[3]]||r[3])}</td><td>${escapeHtml(r[4])}</td></tr>`
  ).join("");
})();

// boot
restart();
