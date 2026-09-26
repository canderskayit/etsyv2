import { FormEvent, useEffect, useRef, useState } from 'react';
import { ArrowUpRight, Check, ChevronRight, CircleCheck, ExternalLink, Film, FolderOpen, Image, Layers, Monitor, Plus, RefreshCw, Settings2, ShieldCheck, Sparkles, X } from 'lucide-react';

type Collection = { name: string; mockup_count: number; video_count: number; ready: boolean };
type Status = { workspace_name: string; data_dir: string; callback_url: string; keys_saved: boolean; etsy_connected: boolean; shop_id: string; photoshop_ready: boolean; photoshop_path: string; mode: string; collections: Collection[]; dependencies: Record<string, boolean> };
async function request<T>(url: string, payload?: unknown): Promise<T> {
  const response = await fetch(url, payload === undefined ? {} : {method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(payload)});
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || 'İşlem tamamlanamadı.');
  return data;
}
export function useStudio() {
  const [status, setStatus] = useState<Status | null>(null);
  const [error, setError] = useState('');
  async function refresh() { try { setStatus(await request<Status>('/api/v2/status')); setError(''); } catch(e) { setError(String(e)); } }
  useEffect(() => { void refresh(); const onFocus = () => { void refresh(); }; window.addEventListener('focus', onFocus); return () => window.removeEventListener('focus', onFocus); }, []);
  return {status, refresh, error};
}
type StudioProps = { status: Status | null; onNavigate: (view: 'home'|'setup'|'library'|'new'|'production'|'settings')=>void; refresh: ()=>Promise<void> };

export function Home({status, onNavigate, products}: StudioProps & {products: {id:string; name:string; status:string; overall_progress:number}[]}) {
  const ready = status?.collections.filter(c=>c.ready).length || 0;
  const active = products.filter(p=>['queued','running'].includes(p.status)).length;
  const done = [status?.keys_saved, status?.etsy_connected, status?.photoshop_ready, ready > 0].filter(Boolean).length;
  return <div className="view-stack studio-home">
    <header className="studio-heading"><div><span className="eyebrow">SENİN MAĞAZAN. SENİN STÜDYON.</span><h1>Fikirden vitrine.</h1><p>Üretimini, şablonlarını ve Etsy mağazanı tek yerden yönet.</p></div><span className="local-badge"><Monitor size={14}/> Bu bilgisayarda çalışıyor</span></header>
    <section className="studio-hero"><div className="hero-copy"><span className="hero-kicker"><span/> ÜRETMEK İÇİN BİR ALAN</span><h2>Tasarımını getir.<br/>Gerisini birlikte<br/><em>hazırlayalım.</em></h2><p>Görsellerini seç, kendi mockuplarınla üret.<br/>Hazır olduğunda Etsy’ye taslak olarak gönder.</p><button className="button primary large" onClick={()=>onNavigate('new')}><Plus/> Yeni ürün oluştur <ArrowUpRight/></button></div><div className="hero-art" aria-hidden="true"><div className="art-orbit"/><div className="poster rear"><div className="sun"/><div className="landscape"/></div><div className="poster front"><span>THE ART OF</span><b>slow<br/>living.</b><div className="art-arch"><i/><i/></div><small>MAKE ROOM FOR WHAT MATTERS</small></div><div className="art-chip"><CircleCheck/> Kendi şablonlarınla üret</div><span className="art-caption">YOUR NEXT COLLECTION STARTS HERE</span></div></section>
    <div className="studio-metrics"><div><span><Layers/> Yerel ürünler</span><strong>{products.length}<small>ürün</small></strong></div><div><span><Sparkles/> Üretimde</span><strong>{active}<small>işlem</small></strong></div><div><span><Image/> Hazır koleksiyonlar</span><strong>{ready}<small>koleksiyon</small></strong></div><div><span><ShieldCheck/> Çalışma modu</span><strong className="text-metric">{status?.mode === 'draft' ? 'Etsy taslak' : 'Deneme'}<small>{status?.mode === 'draft' ? 'Yeni ürünler taslak olur' : 'Etsy’ye ürün gönderilmez'}</small></strong></div></div>
    <div className="home-bottom"><section className="studio-card"><div className="card-title"><div><span className="eyebrow">BAŞLANGIÇ REHBERİ</span><h2>Stüdyonu kendine göre kur</h2></div><span className="count-badge">{done} / 4</span></div><div className="setup-progress"><i style={{width:`${done*25}%`}}/></div>{[['API anahtarlarını kaydet',status?.keys_saved],['Etsy mağazanı bağla',status?.etsy_connected],['Photoshop’u seç',status?.photoshop_ready],['İlk koleksiyonunu ekle',ready>0]].map(([label,complete],i)=><button className="setup-row" key={i} onClick={()=>onNavigate(i===3?'library':'setup')}><span className={complete?'done':''}>{complete?<Check size={15}/>:String(i+1).padStart(2,'0')}</span><b>{label}</b><ChevronRight size={16}/></button>)}</section><section className="studio-card activity-card"><div className="card-title"><div><span className="eyebrow">ÜRETİM MASASI</span><h2>Son çalışmaların</h2></div><button className="icon-button" aria-label="Üretim akışını aç" onClick={()=>onNavigate('production')}><ArrowUpRight size={18}/></button></div>{products.length ? products.slice(0,4).map(p=><button className="activity-row" key={p.id} onClick={()=>onNavigate('production')}><span><Image size={18}/></span><div><b>{p.name}</b><small>%{p.overall_progress || 0} tamamlandı</small></div><ChevronRight size={16}/></button>):<div className="studio-empty"><div><Layers size={28}/></div><h3>İlk ürününe yer açtık.</h3><p>Eklediğin ürünler ve üretim ilerlemesi<br/>burada görünecek.</p><button className="text-link" onClick={()=>onNavigate('new')}>Ürün oluşturmaya başla →</button></div>}</section></div>
  </div>;
}

export function Setup({status, refresh, onNavigate}: StudioProps) {
  const [busy, setBusy] = useState(''), [message,setMessage] = useState(''), [error,setError] = useState('');
  async function perform(key:string, job:()=>Promise<void>) { setBusy(key); setMessage(''); setError(''); try { await job(); await refresh(); } catch(e) {setError(e instanceof Error?e.message:String(e));} finally{setBusy('');} }
  function save(event:FormEvent<HTMLFormElement>) { event.preventDefault(); const form=event.currentTarget; const data=new FormData(form); void perform('keys',async()=>{await request('/api/settings',Object.fromEntries(data.entries())); form.reset(); setMessage('API bilgilerin bu bilgisayara kaydedildi. Şimdi Etsy hesabını bağlayabilirsin.');}); }
  async function connect() { const popup=window.open('about:blank','etsy-v2-oauth','width=760,height=850'); await perform('oauth',async()=>{try {const data=await request<{authorize_url:string}>('/api/etsy/oauth/start'); if(popup) popup.location.href=data.authorize_url; else window.location.assign(data.authorize_url); }catch(e){popup?.close();throw e;}}); }
  return <div className="view-stack"><header className="studio-heading"><div><span className="eyebrow">SANA ÖZEL ÇALIŞMA ALANI</span><h1>Stüdyonu bağla.</h1><p>Her bilgisayar kendi mağazası, ayarları ve dosyalarıyla çalışır.</p></div><button className="button" onClick={()=>void refresh()}><RefreshCw/> Durumu yenile</button></header>{message&&<div role="status" className="inline-message">{message}</div>}{error&&<div role="alert" className="inline-message error">{error}</div>}
    <div className="setup-grid"><section className="studio-card setup-card"><div className="card-title"><span className="step-number">01</span><div><h2>Etsy uygulama bilgileri</h2><p>Kendi Etsy uygulamanın anahtarlarını kullan.</p></div>{status?.keys_saved&&<CircleCheck className="ok-icon"/>}</div><form onSubmit={save}><label className="field">Çalışma alanı adı<input name="workspace_name" defaultValue={status?.workspace_name} placeholder="Örn. Duru’nun stüdyosu" maxLength={60}/></label><label className="field">Keystring<input name="etsy_keystring" type="password" autoComplete="off" placeholder={status?.keys_saved?'Kayıtlı · değiştirmek için yaz':'Etsy API keystring'} required={!status?.keys_saved}/></label><label className="field">Shared Secret<input name="etsy_shared_secret" type="password" autoComplete="new-password" placeholder={status?.keys_saved?'Kayıtlı · değiştirmek için yaz':'Etsy API shared secret'} required={!status?.keys_saved}/></label><button className="button primary" disabled={!!busy}>{busy==='keys'?'Kaydediliyor…':'Bilgileri kaydet'}</button></form><a className="subtle-link" href="https://www.etsy.com/developers/your-apps" target="_blank" rel="noreferrer">Etsy uygulamalarımı aç <ExternalLink size={13}/></a></section>
    <section className="studio-card setup-card"><div className="card-title"><span className="step-number">02</span><div><h2>Mağazanı yetkilendir</h2><p>API bilgilerini kaydettikten sonra bağlan.</p></div>{status?.etsy_connected&&<CircleCheck className="ok-icon"/>}</div><div className="callback-box"><span>Etsy uygulamasına eklenecek callback adresi</span><code>{status?.callback_url || 'http://localhost:8766/oauth/etsy/callback'}</code><small>Adres, Etsy uygulamasındaki Redirect URI ile birebir aynı olmalı.</small></div><div className="connection-card"><span className={`connection-dot ${status?.etsy_connected?'online':''}`}/><div><b>{status?.etsy_connected?'Mağaza bağlantısı kayıtlı':'Mağazan henüz bağlı değil'}</b><small>{status?.shop_id?`Mağaza ID: ${status.shop_id}`:'Etsy izin ekranını tamamlayarak bağlan.'}</small></div></div><button className="button primary" disabled={!!busy||!status?.keys_saved} onClick={()=>void connect()}><ExternalLink/>{status?.etsy_connected?'Yeniden yetkilendir':'Etsy hesabını bağla'}</button>{status?.keys_saved&&<button className="text-link disconnect" disabled={!!busy} onClick={()=>{if(confirm('Bu bilgisayardaki Etsy anahtarları ve bağlantısı kaldırılsın mı? Ürün dosyaları korunur.')) void perform('disconnect',async()=>{await request('/api/v2/disconnect',{confirmation:'disconnect'});setMessage('Etsy bağlantısı kaldırıldı. Deneme modu açıldı.');});}}>Bağlantıyı bu bilgisayardan kaldır</button>}</section>
    <section className="studio-card setup-card"><div className="card-title"><span className="step-number">03</span><div><h2>Photoshop ve şablonlar</h2><p>Üretim, bilgisayarındaki Photoshop ile yapılır.</p></div>{status?.photoshop_ready&&<CircleCheck className="ok-icon"/>}</div><div className="connection-card"><Monitor/><div><b>{status?.photoshop_ready?'Photoshop bulundu':'Photoshop seçilmesi gerekiyor'}</b><small className="break-path">{status?.photoshop_path||'Photoshop.exe dosyasını seç.'}</small></div></div><button className="button" disabled={!!busy} onClick={()=>void perform('photoshop',async()=>{const data=await request<{paths:string[]}>('/api/v2/pick',{kind:'photoshop'});if(data.paths[0])await request('/api/settings',{photoshop_exe_path:data.paths[0]});})}><FolderOpen/>{busy==='photoshop'?'Dosya penceresinden seç…':'Photoshop’u seç'}</button><button className="button" onClick={()=>onNavigate('library')}><Layers/> Mockup ve video kütüphanesini aç</button><p className="hint">PSD dosyalarında değiştirilecek görsel bir Smart Object olmalı. Katman adı varsayılan olarak “Kare 1”; gelişmiş ayarlardan değiştirebilirsin. Video PSD, kullanılan Photoshop sürümünde video dışa aktarımını desteklemeli.</p></section>
    <section className="studio-card setup-card"><div className="card-title"><span className="step-number">04</span><div><h2>Çalışma tercihlerin</h2><p>Önce deneme yap, sonra taslak üretimine geç.</p></div></div><label className="field">Üretim modu<select disabled={!!busy} value={status?.mode||'dry_run'} onChange={e=>void perform('mode',async()=>{await request('/api/settings',{etsy_mode:e.target.value});setMessage('Çalışma modu güncellendi.');})}><option value="dry_run">Deneme · Etsy’ye gönderme</option><option value="draft">Etsy taslak · mağazada yayınlama</option></select></label><div className="dependency-list">{Object.entries(status?.dependencies||{}).map(([label,ok])=><div key={label}><span>{label}</span><b className={ok?'ok-icon':'warning-text'}>{ok?'Hazır':'Eksik'}</b></div>)}</div><button className="button" onClick={()=>onNavigate('settings')}><Settings2/> Fiyat, CSV ve gelişmiş ayarlar</button><p className="hint">Yerel dosyaların: <code className="break-path">{status?.data_dir}</code></p></section></div>
  </div>;
}

export function Library({status,refresh}:StudioProps) {
  const [name,setName]=useState('');
  const [mockups,setMockups]=useState<File[]>([]);
  const [video,setVideo]=useState<File|null>(null);
  const [busy,setBusy]=useState(false),[error,setError]=useState(''),[message,setMessage]=useState('');
  const [progress,setProgress]=useState('');
  const mockupInput=useRef<HTMLInputElement>(null),videoInput=useRef<HTMLInputElement>(null);
  const uploaded=useRef(new Map<File,string>());
  function selectMockups(files:File[]) {
    if(!files.length)return;
    if(files.length>19||files.some(file=>!file.name.toLowerCase().endsWith('.psd')||!file.size||file.size>4*1024**3)) {
      setError('1–19 PSD dosyası seçin. Her dosya dolu ve en fazla 4 GB olmalı.');return;
    }
    setError('');setMessage('');setMockups(files);
  }
  function selectVideo(file:File|undefined) {
    if(!file)return;
    if(!/\.(psd|mp4|mov)$/i.test(file.name)||!file.size||file.size>4*1024**3) {
      setError('PSD, MP4 veya MOV seçin. Dosya dolu ve en fazla 4 GB olmalı.');return;
    }
    setError('');setMessage('');setVideo(file);
  }
  async function upload(file:File,kind:'mockup'|'video') {
    const cached=uploaded.current.get(file);
    if(cached)return cached;
    const response=await fetch(`/api/v2/library-files?${new URLSearchParams({filename:file.name,kind})}`,{
      method:'POST',headers:{'Content-Type':'application/octet-stream'},body:file
    });
    const data=await response.json();
    if(!response.ok)throw new Error(data.error||`${file.name} aktarılamadı.`);
    uploaded.current.set(file,data.path);
    return data.path as string;
  }
  async function create(event:FormEvent) {
    event.preventDefault();if(busy||!mockups.length)return;
    setBusy(true);setError('');setMessage('');
    try {
      const paths:string[]=[];
      for(const [index,file] of mockups.entries()) {
        setProgress(`Mockup ${index+1}/${mockups.length} aktarılıyor: ${file.name}`);
        paths.push(await upload(file,'mockup'));
      }
      let videoPath='';
      if(video){setProgress(`Video aktarılıyor: ${video.name}`);videoPath=await upload(video,'video');}
      setProgress('Koleksiyon kaydediliyor…');
      await request('/api/v2/collections',{name,mockups:paths,video:videoPath});
      setMessage(`“${name}” koleksiyonu eklendi. Yeni ürün oluştururken seçebilirsin.`);
      setName('');setMockups([]);setVideo(null);uploaded.current.clear();await refresh();
    }catch(e){setError(e instanceof Error?e.message:String(e));}
    finally{setBusy(false);setProgress('');}
  }
  return <div className="view-stack">
    <header className="studio-heading"><div><span className="eyebrow">KENDİ GÖRSEL DÜNYAN</span><h1>Şablon kütüphanesi.</h1><p>Mockuplarını ve videonu bir koleksiyonda topla; her üründe yeniden kullan.</p></div><span className="local-badge"><Layers size={14}/>{status?.collections.filter(c=>c.ready).length||0} hazır koleksiyon</span></header>
    {error&&<div role="alert" className="inline-message error">{error}</div>}
    {message&&<div role="status" className="inline-message">{message}</div>}
    <div className="library-layout">
      <form className="studio-card library-form" onSubmit={create}>
        <div className="card-title"><div><span className="eyebrow">YENİ KOLEKSİYON</span><h2>Vitrinini sen seç.</h2></div><Plus/></div>
        <label className="field">Koleksiyon adı<input required disabled={busy} value={name} onChange={e=>setName(e.target.value)} placeholder="Örn. Minimal yaşam alanları" maxLength={70}/></label>
        <input ref={mockupInput} className="library-file-input" type="file" accept=".psd" multiple disabled={busy} aria-label="Mockup PSD dosyaları" onChange={e=>{selectMockups(Array.from(e.currentTarget.files||[]));e.currentTarget.value='';}}/>
        <button type="button" className="template-picker" disabled={busy} onClick={()=>mockupInput.current?.click()}><Image size={26}/><b>Mockup PSD dosyalarını seç</b><span>Klasörden 1–19 PSD seç · Birden çok dosya için Ctrl tuşunu kullan</span></button>
        {mockups.length>0&&<div className="chosen-files">{mockups.map((file,index)=><div key={`${file.name}-${index}`}><span>{String(index+1).padStart(2,'0')}</span><b>{file.name}</b>{index===0&&<small>Kapak</small>}<button type="button" className="text-link" disabled={busy} onClick={()=>setMockups(mockups.filter((_,i)=>i!==index))} aria-label={`${file.name} kaldır`}><X size={15}/></button></div>)}</div>}
        <input ref={videoInput} className="library-file-input" type="file" accept=".psd,.mp4,.mov" disabled={busy} aria-label="Video veya video şablonu" onChange={e=>{selectVideo(e.currentTarget.files?.[0]);e.currentTarget.value='';}}/>
        <button type="button" className="template-picker video-picker" disabled={busy} onClick={()=>videoInput.current?.click()}><Film size={24}/><b>{video?video.name:'Video veya video şablonu seç'}</b><span>Klasörden seç · İsteğe bağlı · PSD, MP4 veya MOV</span></button>
        {video&&<button className="text-link" type="button" disabled={busy} onClick={()=>setVideo(null)}>Videoyu kaldır</button>}
        <p className="hint">İlk mockup kapak olarak kullanılır. Dosyaların kopyaları bu bilgisayarda saklanır. Hazır MP4/MOV, koleksiyondaki her üründe aynı video olarak kullanılır.</p>
        {progress&&<p role="status" className="hint">{progress}</p>}
        <button className="button primary large" disabled={busy||!mockups.length}>{busy?'Koleksiyon hazırlanıyor…':'Koleksiyonu kaydet'}<ChevronRight/></button>
      </form>
      <div className="collection-stack"><div className="section-heading"><h2>Koleksiyonların</h2><button className="icon-button" aria-label="Koleksiyonları yenile" onClick={()=>void refresh()}><RefreshCw size={17}/></button></div>
        {status?.collections.filter(c=>c.ready).map((c,i)=><article className="collection-card" key={c.name}><div className={`collection-art tone-${i%3}`}><div/><div/><span>{String(i+1).padStart(2,'0')}</span></div><div className="collection-info"><h3>{c.name}</h3><p><Image size={13}/>{c.mockup_count} mockup <Film size={13}/>{c.video_count} video</p><span><CircleCheck size={13}/> Üretime hazır</span></div></article>)}
        {!status?.collections.some(c=>c.ready)&&<div className="studio-card studio-empty"><div><FolderOpen size={28}/></div><h3>Henüz koleksiyon yok.</h3><p>Soldan kendi PSD dosyalarını ve<br/>videonu seçerek başlayabilirsin.</p></div>}
        <div className="library-tip"><ShieldCheck/><div><b>Her stüdyo kendine ait.</b><p>Arkadaşların kendi dosyalarını seçer. Mağaza bilgilerin ve ürünlerin dağıtım paketine eklenmez.</p></div></div>
      </div>
    </div>
  </div>;
}
