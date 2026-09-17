import { FormEvent, useEffect, useState } from 'react'
import { Edit3, Globe2, Image, Plus, Radio, X } from 'lucide-react'
import BaseWorkspacePage, {type Page} from './WorkspacePage'
import CrudModal from './CrudModal'
import SubscriberPage from './SubscriberPage'
import LiveSessionsPage from './LiveSessionsPage'

export default function WorkspacePage(props:{page:Page;query:string;identity?:{role:string}}){
  if(props.page==='Subscribers')return <SubscriberPage query={props.query}/>
  if(props.page==='Live sessions')return <LiveSessionsPage query={props.query}/>
  if(props.page==='IP pools'||props.page==='Routers & sites')return <InfrastructurePage {...props}/>
  if(props.page==='Settings')return <BrandingSettings identity={props.identity}/>
  return <BaseWorkspacePage {...props}/>
}

function InfrastructurePage({page,query}:{page:Page;query:string}){
  const pools=page==='IP pools',endpoint=pools?'/api/ip-pools':'/api/routers'
  const [items,setItems]=useState<any[]>([]),[edit,setEdit]=useState<any>(null),[add,setAdd]=useState(false),[notice,setNotice]=useState('')
  // These records are operational data. Do not let a browser retain an old
  // empty response after an import or a pool edit.
  const load=()=>{fetch(endpoint,{cache:'no-store'}).then(r=>r.json()).then(setItems)}
  useEffect(()=>{load()},[endpoint])
  const shown=items.filter(i=>JSON.stringify(i).toLowerCase().includes(query.toLowerCase()))
  async function oneSession(router:any){const response=await fetch(`/api/routers/${router.id}/pppoe-single-session`,{method:'POST'});const result=await response.json();setNotice(response.ok?`Single-session guard enabled on ${router.name}.`:(result.detail??'Could not update the router'));setTimeout(()=>setNotice(''),4000)}
  const columns=pools?['Pool','Type','Range','Used','Utilisation','Actions']:['Router','Loopback IP','Site','RouterOS','State','Actions']
  return <section className="workspace-page">
    <div className="heading"><div><p>WISP workspace</p><h1>{pools?'IP address pools':'Routers & sites'}</h1><span>{pools?'Automatic next-available public and private address allocation.':'MikroTik NAS devices registered by OSPF loopback address.'}</span></div><button className="primary" onClick={()=>setAdd(true)}><Plus size={17}/>{pools?'Add IP pool':'Add router'}</button></div>
    {notice&&<div className="notice">{notice}</div>}
    {add&&<CrudModal page={page} onClose={()=>setAdd(false)} onCreated={load}/>}<article className="table-card"><div className="table-title"><div className="page-icon">{pools?<Globe2/>:<Radio/>}</div><div><b>{pools?'IP address pools':'Routers & sites'}</b><span>{shown.length} {pools?'configured pool':'configured router'}{shown.length===1?'':'s'}</span></div></div><div className="table-wrap"><table><thead><tr>{columns.map(h=><th key={h}>{h}</th>)}</tr></thead><tbody>{shown.map(i=><tr key={i.id}>{pools?<><td>{i.name}</td><td>{i.kind}</td><td>{i.start_address} – {i.end_address}</td><td>{i.used} / {i.total}</td><td>{i.utilisation}%</td></>:<><td>{i.name}</td><td>{i.host}</td><td>{i.site_name}</td><td>{i.routeros_version??'Not checked'}</td><td>{i.reachable?'Reachable':'Offline'}</td></>}<td><div className="row-actions"><button className="secondary" onClick={()=>setEdit(i)}><Edit3 size={14}/> Edit</button>{!pools&&<button className="secondary" onClick={()=>oneSession(i)}>1 session / MAC</button>}</div></td></tr>)}</tbody></table></div>{!shown.length&&<div className="empty">No configured records found.</div>}</article>
    {edit&&<EditInfrastructure pool={pools} item={edit} close={()=>setEdit(null)} saved={()=>{setEdit(null);load()}}/>}
  </section>
}

function EditInfrastructure({pool,item,close,saved}:{pool:boolean;item:any;close:()=>void;saved:()=>void}){
  const [error,setError]=useState('')
  async function submit(e:FormEvent<HTMLFormElement>){e.preventDefault();const body:Record<string,unknown>=Object.fromEntries(new FormData(e.currentTarget));body.enabled=body.enabled==='on';if(!pool&&body.api_port)body.api_port=Number(body.api_port);const r=await fetch(`/api/${pool?'ip-pools':'routers'}/${item.id}`,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});if(!r.ok){setError((await r.json()).detail??'Could not save');return}saved()}
  return <div className="modal-backdrop"><form className="modal" onSubmit={submit}><div className="modal-head"><div><h2>Edit {pool?'IP pool':'router'}</h2><p>{item.name}</p></div><button type="button" onClick={close}><X/></button></div><label>Name<input name="name" defaultValue={item.name} required/></label>{pool?<><label>Type<select name="kind" defaultValue={item.kind}><option value="private">Local / private</option><option value="public">Public</option></select></label><label>First IPv4 address<input name="start_address" defaultValue={item.start_address} required/></label><label>Last IPv4 address<input name="end_address" defaultValue={item.end_address} required/></label></>:<><label>Management / loopback IP<input name="host" defaultValue={item.host} required/></label><label>Site name<input name="site_name" defaultValue={item.site_name} required/></label><label>API port<input name="api_port" type="number" defaultValue={item.api_port}/></label><label>API username<input name="api_username" defaultValue={item.api_username??'admin'}/></label><label>New API password<input name="api_password" type="password" placeholder="Leave blank to keep existing"/></label></>}<label className="check"><input name="enabled" type="checkbox" defaultChecked={item.enabled}/> Enabled</label>{error&&<div className="form-error">{error}</div>}<div className="modal-actions"><button type="button" className="secondary" onClick={close}>Cancel</button><button className="primary">Save changes</button></div></form></div>
}

function BrandingSettings({identity}:{identity?:{role:string}}){
  const [branding,setBranding]=useState<any>({company_name:'WISP',portal_hostname:'',has_logo:false}),[notice,setNotice]=useState(''),[uisp,setUisp]=useState<any>(null),[admins,setAdmins]=useState<any[]>([]),[userError,setUserError]=useState('')
  const superAdmin=identity?.role==='super_admin'
  const loadAdmins=()=>fetch('/api/admin/users').then(r=>r.ok?r.json():[]).then(setAdmins)
  useEffect(()=>{fetch('/api/branding').then(r=>r.json()).then(setBranding);if(superAdmin)loadAdmins()},[superAdmin])
  async function save(e:FormEvent<HTMLFormElement>){e.preventDefault();const body=Object.fromEntries(new FormData(e.currentTarget));const r=await fetch('/api/branding',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});setBranding(await r.json());setNotice('Branding saved')}
  async function logo(file?:File){if(!file)return;const r=await fetch('/api/branding/logo',{method:'PUT',headers:{'Content-Type':file.type},body:file});if(r.ok){setBranding({...branding,has_logo:true});setNotice('Logo uploaded')}else setNotice((await r.json()).detail)}
  async function testUisp(){const response=await fetch('/api/uisp/status');const data=await response.json();setUisp(data)}
  async function createWispUser(e:FormEvent<HTMLFormElement>){e.preventDefault();setUserError('');const data=Object.fromEntries(new FormData(e.currentTarget));const r=await fetch('/api/admin/users',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});if(!r.ok){setUserError((await r.json()).detail??'Could not create WISP user');return}e.currentTarget.reset();setNotice('WISP Administrator created');loadAdmins()}
  return <section className="workspace-page"><div className="heading"><div><p>WISP workspace</p><h1>WISP settings</h1><span>Branding, integrations, retention and platform defaults.</span></div></div>{notice&&<div className="notice">{notice}</div>}<div className="settings-grid"><form className="form-card" onSubmit={save}><h2>WISP branding</h2><p>Net2Net attribution always remains visible.</p><div className="logo-slot">{branding.has_logo?<img src={`/api/branding/logo?t=${Date.now()}`} alt="WISP logo"/>:<Image/>}<label>Upload logo or animated GIF<input type="file" accept="image/png,image/jpeg,image/webp,image/svg+xml,image/gif" onChange={e=>logo(e.target.files?.[0])}/></label></div><label>Company name<input name="company_name" defaultValue={branding.company_name}/></label><label>Portal hostname<input name="portal_hostname" defaultValue={branding.portal_hostname}/></label><button className="primary">Save branding</button></form><section className="form-card"><h2>UISP integration</h2><p>Configure <code>UISP_BASE_URL</code> and <code>UISP_API_TOKEN</code> in the container, then restart it.</p><p>{uisp?uisp.connected?'Connected to local UISP CRM':'Not connected: '+uisp.detail:'Connection not tested.'}</p><button className="secondary" onClick={testUisp}>Test configured connection</button></section><section className="form-card"><h2>RADIUS defaults</h2><label>Suspension rate<input value="8k/8k" readOnly/></label><label>Accounting retention<input value="24 months" readOnly/></label></section>{superAdmin&&<section className="form-card"><h2>WISP administrators</h2><p>WISP Administrators can manage the network but cannot create portal users.</p><form onSubmit={createWispUser}><label>Display name<input name="display_name" required/></label><label>Login username<input name="username" autoComplete="username" required/></label><label>Temporary password<input name="password" type="password" minLength={12} autoComplete="new-password" required/></label>{userError&&<div className="form-error">{userError}</div>}<button className="primary">Add WISP user</button></form><div className="admin-list">{admins.filter(a=>a.role==='wisp_admin').map(a=><p key={a.id}><b>{a.display_name}</b><br/><span>{a.username}</span></p>)||'No WISP administrators yet.'}</div></section>}</div></section>
}

export type {Page}
