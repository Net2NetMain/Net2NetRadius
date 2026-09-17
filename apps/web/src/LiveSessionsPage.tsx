import {Activity, ArrowDown, ArrowUp, Database, Radio, Unplug} from 'lucide-react'
import {useCallback, useEffect, useMemo, useState} from 'react'

type LiveSession={
  id:string; router_id:number; router_name:string; site_name:string; nas_ip_address:string
  username:string; caller_id:string; ip_address:string; uptime:string; interface:string
  download_bps:number; upload_bps:number; download_bytes:number; upload_bytes:number
  download_packets:number; upload_packets:number; duplicate:boolean
}

const rate=(bps:number)=>bps>=1e9?`${(bps/1e9).toFixed(2)} Gbps`:bps>=1e6?`${(bps/1e6).toFixed(2)} Mbps`:bps>=1e3?`${(bps/1e3).toFixed(1)} Kbps`:`${bps} bps`
const bytes=(value:number)=>value>=1e9?`${(value/1e9).toFixed(2)} GB`:value>=1e6?`${(value/1e6).toFixed(2)} MB`:value>=1e3?`${(value/1e3).toFixed(1)} KB`:`${value} B`

export default function LiveSessionsPage({query}:{query:string}){
  const [sessions,setSessions]=useState<LiveSession[]>([])
  const [updated,setUpdated]=useState<Date|null>(null)
  const [error,setError]=useState('')
  const [notice,setNotice]=useState('')
  const load=useCallback(async()=>{
    try{
      const response=await fetch('/api/sessions/live-traffic')
      if(!response.ok)throw new Error('Live traffic API unavailable')
      setSessions(await response.json());setUpdated(new Date());setError('')
    }catch(err){setError(err instanceof Error?err.message:'Could not load live traffic')}
  },[])
  useEffect(()=>{load();const timer=setInterval(load,2000);return()=>clearInterval(timer)},[load])
  const shown=sessions.filter(s=>JSON.stringify(s).toLowerCase().includes(query.toLowerCase()))
  const totals=useMemo(()=>sessions.reduce((a,s)=>({down:a.down+s.download_bps,up:a.up+s.upload_bps,data:a.data+s.download_bytes+s.upload_bytes}),{down:0,up:0,data:0}),[sessions])
  async function disconnect(item:LiveSession){
    if(!confirm(`Disconnect every active session for ${item.username}?`))return
    const response=await fetch(`/api/sessions/live-traffic/${item.router_id}/${encodeURIComponent(item.username)}/disconnect`,{method:'POST'})
    setNotice(response.ok?'PPPoE session disconnected':'The session was no longer active');setTimeout(()=>setNotice(''),3500);load()
  }
  return <section className="workspace-page live-traffic-page">
    <div className="heading"><div><p>WISP workspace</p><h1>Live PPPoE traffic</h1><span>Real-time traffic read directly from each MikroTik PPPoE interface.</span></div></div>
    {notice&&<div className="notice">{notice}</div>}{error&&<div className="form-error">{error}</div>}
    <div className="live-strip"><i/>RouterOS live monitoring · refreshed {updated?.toLocaleTimeString()??'connecting'} · updates every 2 seconds</div>
    <div className="traffic-summary">
      <article><Activity/><div><span>Active sessions</span><strong>{sessions.length}</strong><small>{new Set(sessions.map(s=>s.username)).size} unique users</small></div></article>
      <article><ArrowDown/><div><span>Current download</span><strong>{rate(totals.down)}</strong><small>All active subscribers</small></div></article>
      <article><ArrowUp/><div><span>Current upload</span><strong>{rate(totals.up)}</strong><small>All active subscribers</small></div></article>
      <article><Database/><div><span>Session data</span><strong>{bytes(totals.data)}</strong><small>Since current sessions connected</small></div></article>
    </div>
    <article className="table-card"><div className="table-title"><div className="page-icon"><Radio size={19}/></div><div><b>Connected subscribers</b><span>{shown.length} RouterOS sessions</span></div></div><div className="table-wrap"><table><thead><tr><th>Subscriber</th><th>Router / site</th><th>Address</th><th>Live speed</th><th>Session data</th><th>Uptime</th><th>State</th><th>Actions</th></tr></thead><tbody>{shown.map(item=><tr key={item.id}><td><b>{item.username}</b><span className="cell-note">{item.caller_id||'No caller ID'}</span></td><td>{item.router_name}<span className="cell-note">{item.site_name} · {item.nas_ip_address}</span></td><td>{item.ip_address}</td><td><div className="rate-pair"><span className="download"><ArrowDown size={13}/>{rate(item.download_bps)}</span><span className="upload"><ArrowUp size={13}/>{rate(item.upload_bps)}</span></div></td><td><b>{bytes(item.download_bytes+item.upload_bytes)}</b><span className="cell-note">↓ {bytes(item.download_bytes)} · ↑ {bytes(item.upload_bytes)}</span></td><td>{item.uptime}</td><td>{item.duplicate?<span className="badge duplicate">Duplicate</span>:<span className="badge active"><i/> Live</span>}</td><td><button className="danger-btn" onClick={()=>disconnect(item)}><Unplug size={14}/> Disconnect</button></td></tr>)}</tbody></table></div>{!shown.length&&<div className="empty">No PPPoE sessions are active on the reachable MikroTik routers.</div>}</article>
  </section>
}
