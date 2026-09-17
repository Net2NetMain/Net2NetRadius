import { Bell, ChevronDown, LogOut, UserRound } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'

type Identity={username:string;display_name:string;role:string}
export default function TopControls({identity,onLogout,alerts=[]}:{identity:Identity;onLogout:()=>void;alerts?:{message:string}[]}){
  const [panel,setPanel]=useState<'alerts'|'account'|null>(null)
  const controlsRef=useRef<HTMLDivElement>(null)
  const initials=identity.display_name.split(' ').map(x=>x[0]).join('').slice(0,2).toUpperCase()

  useEffect(()=>{
    const close=(event:PointerEvent)=>{
      if(!controlsRef.current?.contains(event.target as Node)) setPanel(null)
    }
    const escape=(event:KeyboardEvent)=>{
      if(event.key==='Escape') setPanel(null)
    }
    document.addEventListener('pointerdown',close)
    document.addEventListener('keydown',escape)
    return()=>{
      document.removeEventListener('pointerdown',close)
      document.removeEventListener('keydown',escape)
    }
  },[])

  return <div className="top-controls" ref={controlsRef}><button className="icon labelled-icon" onClick={()=>setPanel(panel==='alerts'?null:'alerts')} aria-label="Notifications"><Bell size={19}/>{alerts.length>0&&<span/>}</button><button className="profile-trigger" onClick={()=>setPanel(panel==='account'?null:'account')}><span className="avatar">{initials}</span><span className="user"><b>{identity.display_name}</b><small>{identity.role==='super_admin'?'Super Admin':'WISP Admin'}</small></span><ChevronDown size={15}/></button>{panel&&<div className="top-popover">{panel==='alerts'?<><h3>Notifications</h3>{alerts.length?alerts.map(a=><div className="notification-item" key={a.message}>{a.message}</div>):<div className="popover-empty"><Bell/><b>No new notifications</b><span>Router, duplicate-login and UISP alerts will appear here.</span></div>}</>:<><h3>Account</h3><div className="account-summary"><UserRound/><div><b>{identity.display_name}</b><span>{identity.username}</span><small>{identity.role.replace('_',' ')}</small></div></div><div className="session-detail">Signed in to this local WISP server</div><button className="logout-action" onClick={onLogout}><LogOut size={16}/> Log out</button></>}</div>}</div>
}
