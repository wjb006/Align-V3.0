(async()=>{
const status=document.querySelector('#status');
const panel=document.querySelector('#key-panel');
const secret=document.querySelector('#secret');
const account=document.querySelector('#account');
const code=document.querySelector('#code');
let started=false;
async function request(path,body){
 const response=await fetch(path,{method:body===undefined?'GET':'POST',credentials:'same-origin',headers:body===undefined?{'Accept':'application/json'}:{'Content-Type':'application/json','Accept':'application/json'},body:body===undefined?undefined:JSON.stringify(body),cache:'no-store'});
 const data=await response.json().catch(()=>({message:'The server returned an unreadable response.'}));
 if(!response.ok)throw new Error(data.message||data.error||('Request failed ('+response.status+').'));
 return data;
}
try{
 const me=await request('/api/beta/me');
 if(!me.authenticated||!me.user){location.replace('/login');return;}
 if(!me.user.is_owner){status.textContent='This setup page is for the Align Owner account. Sign in with the Owner account to continue.';return;}
 if(me.user.totp_enabled){status.textContent='Two-step sign-in is already enabled for this Owner account. Do not restart setup. You can return to sign in.';return;}
 const setup=await request('/api/beta/totp/start',{});
 if(!setup.secret){throw new Error('The server did not return an authenticator setup key.');}
 secret.value=setup.secret;
 account.value='Align V3.0 ('+me.user.email+')';
 panel.hidden=false;
 status.textContent='Your private setup key is ready. Add it to your authenticator, then enter the current six-digit code below.';
 started=true;
}catch(error){status.textContent=error.message||'Could not start authenticator setup. Please sign in again and retry.';}
document.querySelector('#copy').addEventListener('click',async()=>{
 try{await navigator.clipboard.writeText(secret.value);status.textContent='Setup key copied. Paste it only into your authenticator app.';}
 catch(_){secret.focus();secret.select();status.textContent='Select and copy the setup key manually. Keep it private.';}
});
document.querySelector('#confirm-form').addEventListener('submit',async event=>{
 event.preventDefault();
 if(!started)return;
 const value=code.value.replace(/\D/g,'');
 if(!/^\d{6}$/.test(value)){status.textContent='Enter the six-digit code from your authenticator.';return;}
 const button=event.currentTarget.querySelector('button[type="submit"]');
 button.disabled=true;status.textContent='Checking your code…';
 try{
  await request('/api/beta/totp/confirm',{code:value});
  panel.hidden=true;
  status.textContent='Two-step sign-in is enabled. Align has signed out your sessions for security. Sign in again with your password and then your authenticator code.';
  setTimeout(()=>location.replace('/login?totp=enabled'),1800);
 }catch(error){status.textContent=error.message||'The code could not be confirmed. Check your authenticator clock and try the current code.';button.disabled=false;}
});
})();