const { contextBridge, ipcRenderer } = require('electron')
const invoke = (method,...args) => ipcRenderer.invoke('reality:'+method,...args)
contextBridge.exposeInMainWorld('reality', {
  initial:()=>invoke('initial'), importProfile:value=>invoke('import',value), removeProfile:id=>invoke('remove',id),
   selectProfile:id=>invoke('select',id), connect:mode=>invoke('connect',mode), disconnect:()=>invoke('disconnect'), recheck:()=>invoke('recheck'),
  savePrefs:prefs=>invoke('prefs',prefs), interfaces:()=>invoke('interfaces'), clipboard:()=>invoke('clipboard'),
  startup:()=>invoke('startup'), setStartup:enabled=>invoke('setStartup',enabled),
  copyAccess:id=>invoke('copyAccess',id), diagnostics:()=>invoke('diagnostics'),
  minimize:()=>invoke('minimize'), close:()=>invoke('close'),
  onState:listener=>{const fn=(_event,state)=>listener(state);ipcRenderer.on('reality:state',fn);return()=>ipcRenderer.removeListener('reality:state',fn)}
})
