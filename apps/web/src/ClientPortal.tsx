import { LogOut } from 'lucide-react'
import { useEffect, useState } from 'react'
import Brand from './Brand'

type Identity={username:string;display_name:string;role:string}

export default function CustomerPortal({identity,onLogout}:{identity:Identity;onLogout:()=>void}) {
  const [data,setData]=useState<any>(null)
  const [running,setRunning]=useState(false)
  const [result,setResult]=useState<any>(null)
  useEffect(()=>{const load=()=>fetch('/api/client/portal',{cache:'no-store'}).then(r=>r.json()).then(setData);load();const timer=window.setInterval(load,2000);return()=>window.clearInterval(timer)},[])
  async function testSpeed(){
    setRunning(true)
    const pings:number[]=[]
    for(let i=0;i<5;i++){const start=performance.now();await fetch(`/api/speed-test/ping?t=${Date.now()}`,{cache:'no-store'});pings.push(performance.now()-start)}
    const downStart=performance.now();const download=await fetch(`/api/speed-test/download?bytes_count=10000000&t=${Date.now()}`,{cache:'no-store'});const blob=await download.blob();const downSeconds=(performance.now()-downStart)/1000
    const uploadData=new Uint8Array(5_000_000);crypto.getRandomValues(uploadData.subarray(0,65536));const upStart=performance.now();await fetch('/api/speed-test/upload',{method:'POST',body:uploadData});const upSeconds=(performance.now()-upStart)/1000
    const latency=pings.reduce((a,b)=>a+b,0)/pings.length
    const diagnostic={download_mbps:Number((blob.size*8/downSeconds/1e6).toFixed(2)),upload_mbps:Number((uploadData.byteLength*8/upSeconds/1e6).toFixed(2)),latency_ms:Number(latency.toFixed(2)),jitter_ms:Number((Math.max(...pings)-Math.min(...pings)).toFixed(2)),packet_loss_percent:0,user_agent:navigator.userAgent,operating_system:navigator.platform,device:/Mobi/.test(navigator.userAgent)?'Mobile':'Desktop',screen:`${screen.width}x${screen.height}`,language:navigator.language,connection:(navigator as any).connection?.effectiveType??'unknown',tested_to:location.host}
    await fetch('/api/speed-tests',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(diagnostic)})
    setResult(diagnostic);setRunning(false)
  }
  if(!data)return <div className="portal-loading">Loading your connection…</div>
  const live=data.live_session??data.sessions.find((s:any)=>!s.stopped_at)
  const liveIp=live?.ip_address??live?.framed_ip_address
  const historyUsage=data.sessions.reduce((n:number,s:any)=>n+Number(s.input_bytes)+Number(s.output_bytes),0)
  const usage=Math.max(historyUsage,Number(live?.download_bytes??0)+Number(live?.upload_bytes??0))
  const rate=(bps:any)=>`${(Number(bps??0)/1_000_000).toFixed(2)} Mbps`
  return <div className="client-shell">
    <header><Brand compact/><span className="client-spacer"/><b>{identity.display_name}</b><button className="secondary" onClick={onLogout}><LogOut size={16}/> Log out</button></header>
    <main className="client-main"><p className="eyebrow">CUSTOMER PORTAL</p><h1>Your internet connection</h1>
      <div className="client-metrics"><article><span>Connection</span><strong className={live?'good':'bad'}>{live?'Online':'Offline'}</strong><small>{liveIp??'No active PPPoE session'}</small></article><article><span>Package</span><strong>{data.package.advertised_down_mbps}/{data.package.advertised_up_mbps} Mbps</strong><small>Provisioned at {data.package.provisioned_down_mbps}/{data.package.provisioned_up_mbps} Mbps</small></article><article><span>Usage this session</span><strong>{(usage/1e9).toFixed(2)} GB</strong><small>{live?'Live RouterOS counters':'No active PPPoE session'}</small></article><article><span>Account status</span><strong>{data.subscriber.status}</strong><small>Managed by your WISP</small></article></div>
      <section className="client-panel"><h2>Account information</h2><dl><div><dt>PPPoE username</dt><dd>{data.subscriber.username}</dd></div><div><dt>Assigned IP</dt><dd>{data.subscriber.framed_ip_address}</dd></div><div><dt>Service site</dt><dd>{data.subscriber.site_name}</dd></div><div><dt>UISP account</dt><dd>{data.subscriber.uisp_link_confirmed?'Linked':'Awaiting WISP link'}</dd></div></dl></section>
      <section className="client-panel"><h2>Live traffic</h2><p>Current traffic from your PPPoE session · refreshes every 2 seconds</p>{live?<dl><div><dt>Download now</dt><dd>{rate(live.download_bps)}</dd></div><div><dt>Upload now</dt><dd>{rate(live.upload_bps)}</dd></div><div><dt>Connected for</dt><dd>{live.uptime}</dd></div><div><dt>Data this session</dt><dd>{(usage/1e9).toFixed(2)} GB</dd></div></dl>:<div className="empty">No active PPPoE session.</div>}</section>
      <section className="client-panel speed-card"><h2>Speed test to WISP core</h2><p>This measures your connection to the WISP core, not a public internet server. Pause streaming, downloads and updates, disconnect unused devices, and use Ethernet when possible. On Wi-Fi, stay close to the router. The test measures latency, jitter, download and upload, and saves device diagnostics for WISP support.</p>{!data.speed_test.eligible&&<div className="speed-warning"><b>Test unavailable on this connection</b><span>{data.speed_test.reason} Your current address is {data.speed_test.source_ip}; the active PPPoE address is {data.speed_test.required_ip}.</span></div>}<button className="primary" onClick={testSpeed} disabled={running||!data.speed_test.eligible}>{running?'Testing latency, download and upload…':'Start speed test'}</button>{result&&<div className="speed-result"><strong>{result.download_mbps} Mbps down</strong> · <strong>{result.upload_mbps} Mbps up</strong><span> · {result.latency_ms} ms latency · {result.jitter_ms} ms jitter</span></div>}</section>
      <section className="client-panel"><h2>Connection history</h2><div className="history-list">{data.sessions.map((s:any)=><div key={s.id}><b>{s.started_at?.replace('T',' ').slice(0,16)??'Pending'}</b><span>{s.stopped_at?'Ended':'Online'} · {((s.input_bytes+s.output_bytes)/1e6).toFixed(1)} MB</span></div>)}</div></section>
    </main><footer>Powered by Net2Net Local RADIUS Manager</footer>
  </div>
}
