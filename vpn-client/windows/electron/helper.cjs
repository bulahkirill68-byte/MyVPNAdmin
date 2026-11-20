const {app}=require('electron')
const fs=require('node:fs/promises')
const path=require('node:path')
const http=require('node:http')
const crypto=require('node:crypto')
const {execFile}=require('node:child_process')
const {promisify}=require('node:util')
const exec=promisify(execFile)
const {parseVless}=require('../shared/profile.cjs')
const {buildConfig,validatePrefs}=require('../shared/config.cjs')
 const {control}=require('./proxy.cjs')
async function hash(file){return crypto.createHash('sha256').update(await fs.readFile(file)).digest('hex')}
async function helper(sessionPath){
 let corePid=0,server,folder,interval,stopping=false,metadata={phase:'starting'}
 const {safeStorage}=require('electron')
 const session=JSON.parse(safeStorage.decryptString(await fs.readFile(sessionPath)))
 if(!/^[a-f0-9]{64}$/.test(session.token)||!Number.isInteger(session.parentPid)||session.parentPid<4||!Number.isInteger(session.port)||session.port<1024||session.port>65535||Math.abs(Date.now()-session.created)>180000)throw Error('Invalid helper session')
 const profile=parseVless(session.uri),prefs=validatePrefs(session.prefs)
 const assets=app.isPackaged?process.resourcesPath:path.join(__dirname,'../assets')
  const engine=path.join(assets,'engine/xray.exe'),stopper=path.join(assets,'native/StopConsole.exe')
 const integrity=JSON.parse(await fs.readFile(path.join(assets,'engine/integrity.json'),'utf8'))
  const hashes=await Promise.all([hash(engine),hash(stopper),hash(path.join(assets,'native/RuntimeControl.exe'))])
  if(hashes[0]!==integrity['xray.exe']||hashes[1]!==integrity['StopConsole.exe']||hashes[2]!==integrity['RuntimeControl.exe'])throw Error('VPN binary integrity check failed')
 async function alive(pid){try{process.kill(pid,0);return true}catch{return false}}
 async function stop(){if(stopping)return;stopping=true;clearInterval(interval)
  if(corePid&&await alive(corePid)){try{await exec(stopper,[String(corePid)],{windowsHide:true,timeout:3000})}catch{}
   const end=Date.now()+5000;while(Date.now()<end&&await alive(corePid))await new Promise(r=>setTimeout(r,200))
   if(await alive(corePid))await exec('taskkill.exe',['/PID',String(corePid),'/T','/F'],{windowsHide:true}).catch(()=>{})}
  server?.close();if(folder)await fs.rm(folder,{recursive:true,force:true});app.exit(0)
 }
 server=http.createServer(async(req,res)=>{
  if(req.headers.authorization!==`Bearer ${session.token}`){res.writeHead(401).end();return}
  if(req.method==='GET'&&req.url==='/state'){res.setHeader('Content-Type','application/json');res.end(JSON.stringify({...metadata,corePid}));return}
  if(req.method==='POST'&&req.url==='/stop'){res.end('{}');void stop();return}
  res.writeHead(404).end()
 })
 await new Promise((resolve,reject)=>{server.once('error',reject);server.listen(session.port,'127.0.0.1',resolve)})
 try{
  const base=path.join(process.env.ProgramData||'C:/ProgramData','RealityVPNClient')
  await fs.mkdir(base,{recursive:true})
  if((await fs.lstat(base)).isSymbolicLink())throw Error('Unsafe runtime directory')
  await exec('icacls.exe',[base,'/inheritance:r','/grant:r','*S-1-5-32-544:(OI)(CI)F','*S-1-5-18:(OI)(CI)F'],{windowsHide:true})
  folder=path.join(base,crypto.randomUUID());await fs.mkdir(folder)
  const config=path.join(folder,'config.json')
   // Resolve the endpoint before installing routes/DNS filters. REALITY still uses the original SNI.
    metadata={phase:'starting',stage:'Разрешение адреса сервера'}
    let dnsTimer
    const address=await Promise.race([require('node:dns/promises').lookup(profile.host),new Promise((_,reject)=>{dnsTimer=setTimeout(()=>reject(Error('DNS сервера не ответил за 5 секунд')),5000)})]).finally(()=>clearTimeout(dnsTimer))
   await fs.writeFile(config,JSON.stringify(buildConfig({...profile,host:address.address},prefs,'vpn')))
  const log=path.join(folder,'core.log')
   corePid=Number(await control(['start-core',engine,config,log,path.join(assets,'engine')]));if(!Number.isInteger(corePid)||corePid<4)throw Error('Core launch failed')
   metadata={phase:'running',stage:'Запуск локального туннеля'}
  interval=setInterval(async()=>{if(!await alive(session.parentPid))return void stop();if(!await alive(corePid)){
   const text=await fs.readFile(log+'.err','utf8').catch(()=> 'Ядро VPN завершилось');metadata={phase:'error',error:text.replaceAll(profile.uuid,'[UUID]').slice(-1600)}
   clearInterval(interval);setTimeout(stop,12000)
  }},1000)
 }catch(e){metadata={phase:'error',error:e.message};setTimeout(stop,12000)}
 app.on('before-quit',()=>{void stop()})
}
module.exports={helper}
