#pragma once
const char WEB_PAGE[] = R"HTML(<!doctype html>
<html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>UNO R4 · 사운드보드</title>
<style>
*{box-sizing:border-box}body{margin:0;background:#eef3ee;color:#233b30;font:16px/1.6 system-ui,sans-serif}
main{max-width:640px;margin:30px auto;padding:24px}h1{font-size:25px}p{font-size:14px}
.keys{display:grid;grid-template-columns:1fr 1fr;gap:12px}button{padding:18px 8px;border:1px solid #bdcebf;border-radius:10px;background:#fff;color:#234a35;font:inherit;cursor:pointer}
button:active{background:#d3ecd9}button:disabled{opacity:.5}.stop{background:#fae8e3;color:#903e30}
section{padding:18px;background:#fff;border-radius:12px;margin:18px 0}#status{white-space:pre-wrap}#reply{overflow-wrap:anywhere;font-family:monospace}
</style><main><h1>UNO R4 사운드보드</h1>
<p>보드와 같은 Wi-Fi에서 IP 주소로 제어합니다. 로그인·API 토큰은 없습니다.</p>
<section id="status" role="status">보드 상태 확인 중…</section>
<div class="keys">
<button data-command="1">1 · 오이쉬</button><button data-command="2">2 · 거제야호</button>
<button data-command="3">3 · 러브어택</button><button data-command="4">4 · 데자뷰</button>
<button data-command="p">5 · 처음부터 재생</button><button data-command="s" class="stop">6 · 출력 정지</button>
<button data-command="n">7 · 다음 음원</button><button data-command="b">8 · 이전 음원</button>
<button data-command="0">정지 / 처음부터 재생</button><button data-command="?">DFPlayer 통신 확인</button>
</div>
<section><strong>A0 볼륨: <span id="volume">—</span> / 30</strong><p>실물 가변저항으로 조절합니다. 출력 정지는 앰프 무음 처리이며, 다음 재생은 파일 처음부터 시작합니다.</p>
<p id="message" role="status"></p><p>최근 DFPlayer 응답: <span id="reply">—</span></p></section>
<p>파일: /sound1.mp3 ~ /sound4.mp3 · OLED의 OUTPUT ON은 앰프 상태이며 곡 재생 완료 여부를 뜻하지 않습니다.</p>
</main><script>
const names=['오이쉬','거제야호','러브어택','데자뷰'];
async function refresh(){
 try{const response=await fetch('/status',{cache:'no-store',signal:AbortSignal.timeout(3000)});if(!response.ok)throw Error('상태 조회 실패');const s=await response.json();
 document.querySelector('#status').textContent=`선택 음원: ${s.track} · ${names[s.track-1]}\n출력: ${s.ampKnown?(s.ampOn?'앰프 ON':'무음'):'확인 중'}${s.busy?' · 명령 처리 중':''}\n${s.mode} · ${s.ip}${s.error?'\n확인 필요: '+s.error:''}`;
 document.querySelector('#volume').textContent=s.volume;document.querySelector('#reply').textContent=s.reply||'아직 응답 없음';
 }catch(e){document.querySelector('#status').textContent='보드 연결을 확인하세요. 보드와 같은 Wi-Fi에 연결하고 OLED의 IP 주소를 다시 열어 주세요.';}
}
document.querySelectorAll('[data-command]').forEach(button=>button.onclick=async()=>{
 button.disabled=true;
 try{const response=await fetch('/command',{method:'POST',headers:{'Content-Type':'text/plain'},body:button.dataset.command,signal:AbortSignal.timeout(3000)});if(!response.ok)throw Error('명령 접수 실패');document.querySelector('#message').textContent='명령을 접수했습니다. DFPlayer 처리 결과는 위 상태에서 확인하세요.';await refresh();}
 catch(e){document.querySelector('#message').textContent=e.message;}finally{button.disabled=false;}
});
(async function poll(){await refresh();setTimeout(poll,1000);})();
</script></html>)HTML";
