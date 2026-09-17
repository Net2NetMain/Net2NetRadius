import { Network } from 'lucide-react'
import { useEffect, useState } from 'react'

export default function Brand({compact=false}:{compact?:boolean}){const [brand,setBrand]=useState<any>({company_name:'WISP',has_logo:false});useEffect(()=>{fetch('/api/branding').then(r=>r.json()).then(setBrand)},[]);return <div className={`brand-content ${compact?'compact':''}`}>{brand.has_logo?<img src="/api/branding/logo" alt={`${brand.company_name} logo`}/>:<Network size={24}/>}<div><b>{brand.company_name}</b><small>{compact?'Powered by Net2Net':'WISP workspace'}</small></div></div>}
