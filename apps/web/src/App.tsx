import {
  Activity, Bell, ChevronDown, CircleGauge,
  Database, Gauge, Globe2, LayoutDashboard, Link2, MapPin,
  LogOut, Menu, Network, Radio, Search, Settings, ShieldCheck, Users, Wifi,
} from 'lucide-react'
import { useEffect, useState } from 'react'
import WorkspacePage, { type Page } from './WorkspaceRouter'
import CustomerPortal from './ClientPortal'
import Brand from './Brand'
import TopControls from './TopControls'

type Summary = {
  subscribers: number; online: number; suspended: number; unlinked: number;
  routers_online: number; routers_total: number; public_ips_used: number;
  public_ips_total: number; private_ips_used: number; private_ips_total: number;
  updated_at?:string; session_series?:{time:string;sessions:number}[]; session_history_ready?:boolean;
  services?:Record<string,string>; attention?:{type:string;message:string;last_checked_at?:string}[];
}

const fallback: Summary = {
  subscribers: 0, online: 0, suspended: 0, unlinked: 0,
  routers_online: 0, routers_total: 0, public_ips_used: 0,
  public_ips_total: 0, private_ips_used: 0, private_ips_total: 0,
}

const nav = [
  [LayoutDashboard, 'Overview'], [Users, 'Subscribers'],
  [Activity, 'Live sessions'], [Gauge, 'Packages'],
  [Globe2, 'IP pools'], [Radio, 'Routers & sites'],
  [Link2, 'UISP links'], [CircleGauge, 'Speed tests'],
  [Database, 'Accounting'], [Settings, 'Settings'],
] as const

function Donut({ value, total, color }: { value: number; total: number; color: string }) {
  const percentage = total ? Math.round((value / total) * 100) : 0
  return <div className="donut" style={{ background: `conic-gradient(${color} ${percentage}%, #e7edf1 0)` }}>
    <div><strong>{percentage}%</strong><span>allocated</span></div>
  </div>
}

type Identity = {username:string;display_name:string;role:'super_admin'|'wisp_admin'|'client'}

function AdminApp({identity,onLogout}:{identity:Identity;onLogout:()=>void}) {
  const [summary, setSummary] = useState(fallback)
  const [menuOpen, setMenuOpen] = useState(false)
  const [apiLive, setApiLive] = useState(false)
  const [activePage, setActivePage] = useState<'Overview' | Page>(() => (sessionStorage.getItem('net2net.active-page') as 'Overview' | Page) || 'Overview')
  const [query, setQuery] = useState('')
  useEffect(() => {
    const load=()=>fetch('/api/dashboard').then(r => r.ok ? r.json() : Promise.reject())
      .then(data => { setSummary(data); setApiLive(true) }).catch(() => setApiLive(false))
    load();const timer=window.setInterval(load,5000);return()=>window.clearInterval(timer)
  }, [])
  useEffect(() => { sessionStorage.setItem('net2net.active-page', activePage) }, [activePage])

  return <div className="shell">
    <aside className={menuOpen ? 'open' : ''}>
      <div className="brand-mark"><Brand/></div>
      <div className="instance"><span>Local managed instance</span><b>Production workspace</b><ChevronDown size={15}/></div>
      <nav>{nav.map(([Icon, label]) => <button className={activePage === label ? 'active' : ''} key={label} onClick={() => { setActivePage(label); setMenuOpen(false) }}>
        <Icon size={18}/><span>{label}</span>{label === 'UISP links' && summary.unlinked>0 && <em>{summary.unlinked}</em>}
      </button>)}</nav>
      <div className="powered"><ShieldCheck size={17}/><div><span>Powered by</span><b>Net2Net Local<br/>RADIUS Manager</b></div></div>
    </aside>

    <main>
      <header>
        <button className="menu" onClick={() => setMenuOpen(!menuOpen)}><Menu/></button>
        <div className="search"><Search size={18}/><input value={query} onChange={event => setQuery(event.target.value)} placeholder="Search the current page..."/></div>
        <div className={`system ${apiLive ? 'live' : ''}`}><i/>{apiLive ? 'API connected' : 'Preview mode'}</div>
        <TopControls identity={identity} onLogout={onLogout} alerts={summary.attention}/>
      </header>

      <section className="content">{activePage === 'Overview' ? <>
        <div className="heading"><div><p>{new Intl.DateTimeFormat(undefined,{dateStyle:'full',timeStyle:'medium'}).format(new Date())}</p><h1>Network overview</h1><span>Live WISP data · refreshed {summary.updated_at?new Date(summary.updated_at).toLocaleTimeString():'connecting…'}</span></div>
          <button className="primary" onClick={() => setActivePage('Subscribers')}><Users size={17}/> Add subscriber</button></div>

        <div className="metrics">
          <article><div className="metric-icon blue"><Users/></div><span>Total subscribers</span><strong>{summary.subscribers}</strong><small>Live production records</small></article>
          <article><div className="metric-icon green"><Wifi/></div><span>Online now</span><strong>{summary.online}</strong><small><b>{summary.subscribers?Math.round(summary.online/summary.subscribers*100):0}%</b> of subscribers</small></article>
          <article><div className="metric-icon amber"><Gauge/></div><span>Suspended</span><strong>{summary.suspended}</strong><small>Limited to 8k/8k</small></article>
          <article><div className="metric-icon violet"><Link2/></div><span>Needs UISP link</span><strong>{summary.unlinked}</strong><small>Awaiting confirmation</small></article>
        </div>

        <div className="grid">
          <article className="panel span2"><div className="panel-head"><div><h2>Sessions today</h2><p>Live RouterOS sessions with RADIUS accounting history</p></div><select><option>Last 24 hours</option></select></div>
            <div className="chart"><div className="ylabels">{[1,.75,.5,.25,0].map(n=><span key={n}>{Math.round(Math.max(1,...(summary.session_series??[]).map(x=>x.sessions))*n)}</span>)}</div>
              <svg viewBox="0 0 760 210" preserveAspectRatio="none"><polyline className="line" points={(summary.session_series??[]).map((p,i,a)=>`${i*(760/Math.max(a.length-1,1))},${200-(p.sessions/Math.max(1,...a.map(x=>x.sessions)))*180}`).join(' ')}/></svg>
              <div className="xlabels"><span>00:00</span><span>04:00</span><span>08:00</span><span>12:00</span><span>16:00</span><span>20:00</span><span>Now</span></div></div>
          </article>

          <article className="panel"><div className="panel-head"><div><h2>Core services</h2><p>Live platform health</p></div><button className="dots">•••</button></div>
            <div className="services"><div><i className="ok"/><span><b>RADIUS service</b><small>Authentication and accounting</small></span><em>{summary.services?.radius??'Checking'}</em></div><div><i className="ok"/><span><b>Database</b><small>Live application connection</small></span><em>{summary.services?.database??'Checking'}</em></div><div><i className={summary.services?.uisp==='not_configured'?'warn':'ok'}/><span><b>UISP sync</b><small>Local CRM integration</small></span><em className={summary.services?.uisp==='not_configured'?'warning':''}>{summary.services?.uisp==='not_configured'?'Not configured':summary.services?.uisp}</em></div><div><i className={summary.routers_total&&summary.routers_online===summary.routers_total?'ok':'warn'}/><span><b>MikroTik sites</b><small>{summary.routers_total?`${summary.routers_online} of ${summary.routers_total} reachable`:'No production routers configured'}</small></span><em className={summary.routers_total&&summary.routers_online===summary.routers_total?'':'warning'}>{!summary.routers_total?'Not configured':summary.routers_online===summary.routers_total?'Healthy':'Attention'}</em></div></div>
          </article>

          <article className="panel"><div className="panel-head"><div><h2>IP pool usage</h2><p>Automatic address allocation</p></div><Globe2 size={20}/></div>
            <div className="pools"><div><Donut value={summary.private_ips_used} total={summary.private_ips_total} color="#168d91"/><span><b>Private / Local</b><small>{summary.private_ips_used} of {summary.private_ips_total} addresses</small></span></div><div><Donut value={summary.public_ips_used} total={summary.public_ips_total} color="#5b68d9"/><span><b>Public</b><small>{summary.public_ips_used} of {summary.public_ips_total} addresses</small></span></div></div>
          </article>

          <article className="panel span2"><div className="panel-head"><div><h2>Requires attention</h2><p>Items that need an administrator</p></div><button className="text-btn" onClick={() => setActivePage('UISP links')}>View all</button></div>
            {summary.unlinked>0&&<div className="attention"><div className="att-icon purple"><Link2/></div><span><b>{summary.unlinked} subscribers need a UISP link</b><small>Confirm the correct customer before billing automation can act.</small></span><button onClick={() => setActivePage('UISP links')}>Review links</button></div>}
            {summary.attention?.filter(a=>a.type==='router').map(a=><div className="attention" key={a.message}><div className="att-icon orange"><MapPin/></div><span><b>{a.message}</b><small>{a.last_checked_at?`Last checked ${new Date(a.last_checked_at).toLocaleString()}`:'No successful response recorded'}</small></span><button onClick={() => setActivePage('Routers & sites')}>View site</button></div>)}{!summary.attention?.length&&<div className="attention"><span><b>No items require attention</b><small>All configured production services are clear.</small></span></div>}
          </article>
        </div>
      </> : <WorkspacePage page={activePage} query={query} identity={identity}/>}</section>
    </main>
  </div>
}

function Login({onLogin}:{onLogin:(identity:Identity)=>void}){const [error,setError]=useState('');const [busy,setBusy]=useState(false);async function submit(e:React.FormEvent<HTMLFormElement>){e.preventDefault();setBusy(true);setError('');const body=Object.fromEntries(new FormData(e.currentTarget));const r=await fetch('/api/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});setBusy(false);if(!r.ok){setError('Incorrect username or password');return}onLogin(await r.json())}return <main className="login-page"><section className="login-card"><div className="login-logo"><Network/><div><b>Net2Net Local</b><span>RADIUS Manager</span></div></div><h1>Welcome back</h1><p>Administrators use their portal account. Customers use their PPPoE username and password.</p><form onSubmit={submit}><label>Username<input name="username" autoComplete="username" required autoFocus/></label><label>Password<input name="password" type="password" autoComplete="current-password" required/></label>{error&&<div className="form-error">{error}</div>}<button className="primary" disabled={busy}>{busy?'Signing in…':'Sign in'}</button></form><small>Managed by Net2Net · Local WISP system</small></section></main>}

function ClientPortal({identity,onLogout}:{identity:Identity;onLogout:()=>void}){const [data,setData]=useState<any>(null);useEffect(()=>{fetch('/api/client/portal').then(r=>r.json()).then(setData)},[]);if(!data)return <div className="portal-loading">Loading your connection…</div>;const live=data.sessions.find((s:any)=>!s.stopped_at);const usage=data.sessions.reduce((n:number,s:any)=>n+Number(s.input_bytes)+Number(s.output_bytes),0);return <div className="client-shell"><header><div className="login-logo"><Network/><b>Net2Net Local</b></div><span className="client-spacer"/><b>{identity.display_name}</b><button className="secondary" onClick={onLogout}><LogOut size={16}/> Log out</button></header><main className="client-main"><p className="eyebrow">CUSTOMER PORTAL</p><h1>Your internet connection</h1><div className="client-metrics"><article><span>Connection</span><strong className={live?'good':'bad'}>{live?'Online':'Offline'}</strong><small>{live?.framed_ip_address??'No active PPPoE session'}</small></article><article><span>Package</span><strong>{data.package.name}</strong><small>{data.package.advertised_down_mbps}/{data.package.advertised_up_mbps} Mbps</small></article><article><span>Usage history</span><strong>{(usage/1e9).toFixed(2)} GB</strong><small>Last {data.sessions.length} sessions</small></article><article><span>Account status</span><strong>{data.subscriber.status}</strong><small>PPPoE details cannot be changed here</small></article></div><section className="client-panel"><h2>Account information</h2><dl><div><dt>PPPoE username</dt><dd>{data.subscriber.username}</dd></div><div><dt>Assigned IP</dt><dd>{data.subscriber.framed_ip_address}</dd></div><div><dt>Service site</dt><dd>{data.subscriber.site_name}</dd></div><div><dt>UISP account</dt><dd>{data.subscriber.uisp_link_confirmed?'Linked':'Awaiting WISP link'}</dd></div></dl></section><section className="client-panel"><h2>Connection history</h2><div className="history-list">{data.sessions.map((s:any)=><div key={s.id}><b>{s.started_at?.replace('T',' ').slice(0,16)??'Pending'}</b><span>{s.stopped_at?'Ended':'Online'} · {((s.input_bytes+s.output_bytes)/1e6).toFixed(1)} MB</span></div>)}</div></section><section className="client-panel speed-card"><h2>Speed test to WISP core</h2><p>Measures this connection to the local RADIUS/core server. Detailed browser and device diagnostics are saved for WISP support.</p><button className="primary" disabled>Speed-test engine is the next service module</button></section></main><footer>Powered by Net2Net Local RADIUS Manager</footer></div>}

export default function App(){const [identity,setIdentity]=useState<Identity|null|undefined>(undefined);useEffect(()=>{fetch('/api/auth/me').then(r=>r.ok?r.json():null).then(setIdentity).catch(()=>setIdentity(null))},[]);const logout=async()=>{await fetch('/api/auth/logout',{method:'POST'});setIdentity(null)};if(identity===undefined)return <div className="portal-loading">Starting Net2Net…</div>;if(!identity)return <Login onLogin={setIdentity}/>;return identity.role==='client'?<CustomerPortal identity={identity} onLogout={logout}/>:<AdminApp identity={identity} onLogout={logout}/>}
