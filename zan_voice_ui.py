"""Zān's single inline microphone for optional shopping-list dictation.

The browser records mono PCM; only a completed clip is sent to the server,
where Meta Muse Voice Transcribe supplies the text. No API key in JavaScript.
Requires Streamlit custom components v2 (Streamlit >= 1.51).
"""
import streamlit as st

_MIC_HTML = """
<div class="zan-voice-mic-wrap">
  <button class="zan-voice-mic" type="button" data-state="idle" aria-label="Start voice input" title="Start voice input" aria-pressed="false">
    <svg class="zan-icon-mic" viewBox="0 0 24 24" width="21" height="21" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="9" y="2" width="6" height="12" rx="3"/><path d="M5 10v2a7 7 0 0 0 14 0v-2M12 19v3m-4 0h8"/></svg>
    <svg class="zan-icon-stop" viewBox="0 0 24 24" width="22" height="22" fill="currentColor" aria-hidden="true"><rect x="6" y="6" width="12" height="12" rx="2"/></svg>
    <span class="zan-icon-loading" aria-hidden="true"></span>
  </button>
  <span class="zan-voice-mic-note" aria-live="polite" role="status"></span>
</div>
"""

_MIC_CSS = """
.zan-voice-mic-wrap{display:flex;align-items:center;justify-content:center;position:relative;min-height:47px;font-family:'Manrope',sans-serif}
.zan-voice-mic{height:46px;width:46px;display:inline-flex;align-items:center;justify-content:center;border:1px solid #E9C9D8;border-radius:13px;background:#FFF1F6;color:#91466B;cursor:pointer;box-shadow:none;transition:background .18s ease,border-color .18s ease,transform .15s ease;position:relative}
.zan-voice-mic:hover:not(:disabled){background:#FBE0EC;border-color:#C77998;transform:translateY(-1px)}
.zan-voice-mic:focus-visible{outline:2px solid #B84F7E;outline-offset:2px}
.zan-voice-mic .zan-icon-mic{display:block}
.zan-voice-mic .zan-icon-stop,.zan-voice-mic .zan-icon-loading{display:none}
.zan-voice-mic[data-state="recording"]{background:#B84F7E;border-color:#B84F7E;color:white;animation:zan-mic-pulse 1.2s ease-in-out infinite}
.zan-voice-mic[data-state="recording"] .zan-icon-mic{display:none}
.zan-voice-mic[data-state="recording"] .zan-icon-stop{display:block}
.zan-voice-mic[data-state="processing"]{background:#FBE0EC;border-color:#C77998;color:#91466B;cursor:wait}
.zan-voice-mic[data-state="processing"] .zan-icon-mic{display:none}
.zan-voice-mic[data-state="processing"] .zan-icon-loading{display:block;width:18px;height:18px;border:2px solid #D8A6BC;border-top-color:#974966;border-radius:50%;animation:zan-mic-spin .85s linear infinite}
.zan-voice-mic:disabled{transform:none}
.zan-voice-mic-note{position:absolute;top:48px;right:0;white-space:nowrap;font-size:10px;font-weight:600;color:#905770;z-index:2;background:#FFF9FC;padding:2px 5px;border-radius:6px;pointer-events:none}
.zan-voice-mic-note:empty{display:none}
@keyframes zan-mic-pulse{50%{box-shadow:0 0 0 6px rgba(184,79,126,.15)}}
@keyframes zan-mic-spin{to{transform:rotate(360deg)}}
@media(prefers-reduced-motion:reduce){.zan-voice-mic,.zan-voice-mic[data-state="recording"],.zan-voice-mic .zan-icon-loading{transition:none;animation:none}}
"""

_MIC_JS = r"""
export default function ({parentElement, setTriggerValue, data}) {
  const wrap = parentElement.querySelector('.zan-voice-mic-wrap');
  const button = parentElement.querySelector('.zan-voice-mic');
  const note = parentElement.querySelector('.zan-voice-mic-note');
  let stream=null, context=null, source=null, processor=null;
  let chunks=[], recording=false, busy=false, autoStop=null, recovery=null;
  const setUi=(state,message='')=>{
    button.dataset.state=state;
    button.setAttribute('aria-pressed',String(state==='recording'));
    button.setAttribute('aria-label',state==='recording'?'Stop recording':state==='processing'?'Transcribing':'Start voice input');
    button.title=button.getAttribute('aria-label');
    button.disabled=state==='processing';
    note.textContent=message;
  };
  const closeAudio=()=>{
    if(autoStop)clearTimeout(autoStop);autoStop=null;
    if(processor){processor.onaudioprocess=null;try{processor.disconnect();}catch(_){}}
    if(source){try{source.disconnect();}catch(_){}}
    if(stream)stream.getTracks().forEach(t=>t.stop());
    if(context)context.close().catch(()=>{});
    processor=null;source=null;stream=null;context=null;
  };
  const clearRecovery=()=>{if(recovery)clearTimeout(recovery);recovery=null;};
  const acknowledge=()=>{
    const ack=Number(data?.acknowledgement||0);
    const last=Number(wrap.dataset.ack||0);
    if(ack>last){wrap.dataset.ack=String(ack);busy=false;clearRecovery();setUi('idle');}
  };
  acknowledge();
  // If the server stops responding, never trap the user in a disabled mic.
  if(button.dataset.state==='processing'){
    const elapsed=Date.now()-Number(wrap.dataset.processingSince||Date.now());
    recovery=setTimeout(()=>{
      busy=false;setUi('idle','Try again');
    },Math.max(1000,30000-elapsed));
  }
  function wavBase64(samples,sampleRate){
    const targetRate=16000,ratio=sampleRate/targetRate;
    const length=Math.max(1,Math.floor(samples.length/ratio));
    const bytes=new Uint8Array(44+length*2),view=new DataView(bytes.buffer);
    const put=(pos,text)=>{for(let i=0;i<text.length;i++)view.setUint8(pos+i,text.charCodeAt(i));};
    put(0,'RIFF');view.setUint32(4,36+length*2,true);put(8,'WAVE');
    put(12,'fmt ');view.setUint32(16,16,true);view.setUint16(20,1,true);
    view.setUint16(22,1,true);view.setUint32(24,targetRate,true);
    view.setUint32(28,targetRate*2,true);view.setUint16(32,2,true);
    view.setUint16(34,16,true);put(36,'data');view.setUint32(40,length*2,true);
    for(let i=0;i<length;i++){
      const pos=i*ratio,lo=Math.floor(pos),hi=Math.min(samples.length-1,lo+1),t=pos-lo;
      const val=Math.max(-1,Math.min(1,samples[lo]*(1-t)+samples[hi]*t));
      view.setInt16(44+i*2,Math.round(val<0?val*32768:val*32767),true);
    }
    let binary='';
    for(let i=0;i<bytes.length;i+=16384)binary+=String.fromCharCode(...bytes.subarray(i,i+16384));
    return btoa(binary);
  }
  const stop=()=>{
    if(!recording||busy)return;
    recording=false;busy=true;
    const rate=context?.sampleRate||16000;
    closeAudio();
    setUi('processing','Transcribing…');
    wrap.dataset.processingSince=String(Date.now());
    clearRecovery();
    recovery=setTimeout(()=>{busy=false;setUi('idle','Try again');},30000);
    try{
      let count=0;for(const chunk of chunks)count+=chunk.length;
      if(count<rate*.28)throw new Error('Try a slightly longer recording');
      const samples=new Float32Array(count);let offset=0;
      for(const chunk of chunks){samples.set(chunk,offset);offset+=chunk.length;}
      chunks=[];
      setTriggerValue('wav',wavBase64(samples,rate));
    }catch(e){clearRecovery();busy=false;setUi('idle',e.message||'Try again');}
  };
  const start=async()=>{
    if(busy||recording)return;
    if(!navigator.mediaDevices?.getUserMedia){setUi('idle','Microphone unavailable');return;}
    busy=true;button.disabled=true;note.textContent='';
    try{
      stream=await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true},video:false});
      context=new (window.AudioContext||window.webkitAudioContext)();
      source=context.createMediaStreamSource(stream);
      processor=context.createScriptProcessor(2048,1,1);
      chunks=[];
      processor.onaudioprocess=e=>{
        if(recording)chunks.push(new Float32Array(e.inputBuffer.getChannelData(0)));
      };
      source.connect(processor);processor.connect(context.destination);
      recording=true;busy=false;
      setUi('recording','Listening…');
      autoStop=setTimeout(()=>{if(recording)stop();},20000);
    }catch(e){recording=false;closeAudio();busy=false;setUi('idle',e?.name==='NotAllowedError'?'Allow microphone access':'Microphone unavailable');}
  };
  button.onclick=()=>{if(recording)stop();else if(!busy)start();};
  return()=>{closeAudio();clearRecovery();};
}
"""

shopping_mic = st.components.v2.component(
    "zan_shopping_inline_mic",
    html=_MIC_HTML, css=_MIC_CSS, js=_MIC_JS,
)


def render_shopping_mic(*, acknowledgement: int = 0):
    """Return one WAV trigger, and reset the microphone when processing ends."""
    return shopping_mic(
        key="zan_shopping_microphone",
        data={"acknowledgement": acknowledgement},
        on_wav_change=lambda: None,
    )
