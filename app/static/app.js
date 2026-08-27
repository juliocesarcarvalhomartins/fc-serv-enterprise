const state={user:null,view:"pending",invoices:[],filteredInvoices:[],accounts:[],users:[],activities:[],searchTimer:null};
const $=id=>document.getElementById(id);
const esc=value=>String(value??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"})[c]);
const money=value=>value===null||value===""?"—":Number(value).toLocaleString("pt-BR",{style:"currency",currency:"BRL"});
const brDate=value=>value?new Date(`${value}T12:00:00`).toLocaleDateString("pt-BR"):"—";
const apiErrorMessage=data=>{
  const detail=data?.detail??data;
  if(typeof detail==="string"&&detail.trim())return detail;
  if(Array.isArray(detail))return detail.map(item=>item?.msg||item?.message||String(item)).join("; ");
  if(detail&&typeof detail==="object")return detail.message||detail.msg||JSON.stringify(detail);
  return "Não foi possível concluir a operação.";
};

async function api(path,options={}){
  const {timeout=180000,...requestOptions}=options;
  const controller=new AbortController();
  const timer=setTimeout(()=>controller.abort(),timeout);
  try{
    const response=await fetch(path,{...requestOptions,signal:controller.signal,headers:{...(requestOptions.body instanceof FormData?{}:{"Content-Type":"application/json"}),...(requestOptions.headers||{})}});
    if(response.status===401){showAuth(false);throw new Error("Sua sessão expirou. Entre novamente.");}
    const type=response.headers.get("content-type")||"";
    const data=type.includes("application/json")?await response.json():await response.text();
    if(!response.ok)throw new Error(apiErrorMessage(data));
    return data;
  }catch(error){
    if(error.name==="AbortError")throw new Error("A operação demorou demais. Verifique a planilha ou a conexão com o servidor.");
    throw error;
  }finally{clearTimeout(timer)}
}
function toast(message,error=false){const box=$("toast");box.textContent=message;box.className=`toast show${error?" error":""}`;clearTimeout(toast.timer);toast.timer=setTimeout(()=>box.className="toast",error?9000:4500)}
function loading(show,text="Processando..."){$("loadingText").textContent=text;$("loading").classList.toggle("hidden",!show)}
function openModal(html){$("modalContent").innerHTML=html;$("modal").classList.remove("hidden")}
function closeModal(){$("modal").classList.add("hidden");$("modalContent").innerHTML=""}
function showAuth(setup){$("appShell").classList.add("hidden");$("authScreen").classList.remove("hidden");$("setupForm").classList.toggle("hidden",!setup);$("loginForm").classList.toggle("hidden",setup)}
function showApp(user){state.user=user;$("authScreen").classList.add("hidden");$("appShell").classList.remove("hidden");$("userName").textContent=user.name;$("userInitial").textContent=user.name.charAt(0).toUpperCase();$("userRole").textContent=user.role==="owner"?"Proprietário":user.role==="admin"?"Administrador":"Usuário";document.querySelectorAll(".admin-only").forEach(el=>el.classList.toggle("hidden",!["owner","admin"].includes(user.role)));switchView("pending")}

async function bootstrap(){
  try{const user=await api("/api/me");showApp(user)}catch{
    const setup=await fetch("/api/setup/status").then(r=>r.json());showAuth(setup.required)
  }
}
async function loadDashboard(){const data=await api("/api/dashboard");$("statTotal").textContent=data.total;$("statPending").textContent=data.pending;$("statCompleted").textContent=data.completed;$("statGko").textContent=data.gko_pending;$("pendingBadge").textContent=data.pending;$("completedBadge").textContent=data.completed}
async function loadInvoices(){
  const search=$("invoiceSearch").value.trim();
  const bucket=state.view==="completed"?"completed":state.view==="services"||state.view==="review"?"all":"pending";
  const type=state.view==="services"?"SERVICE":state.view==="review"?"REVIEW":"FREIGHT";
  state.invoices=await api(`/api/invoices?bucket=${bucket}&invoice_type=${type}&search=${encodeURIComponent(search)}`);applyExcelFilters()
}
async function refreshCurrentData(){const tasks=[loadDashboard()];if(["pending","completed","services","review"].includes(state.view))tasks.push(loadInvoices());if(state.view==="accounts"&&["owner","admin"].includes(state.user.role))tasks.push(loadAccounts());await Promise.all(tasks)}
function renderInvoices(){
  const list=state.filteredInvoices;
  const rows=$("invoiceRows");$("invoiceEmpty").classList.toggle("hidden",list.length>0);rows.innerHTML=list.map(item=>`<tr>
    <td><span class="carrier">${esc(item.carrier)}</span></td><td>${item.has_source_email?`<button class="invoice-link" data-action="email" data-id="${item.id}" title="Abrir esta fatura no e-mail">${esc(item.invoice_number)}</button>`:`<span class="invoice-number">${esc(item.invoice_number)}</span>`}</td>
    <td>${brDate(item.due_date)}</td><td class="money">${money(item.amount)}</td><td><span class="source-badge ${esc(item.source)}">${item.source==="email"?"E-mail":item.source==="excel"?"Excel":"Manual"}</span></td>
    <td><button class="toggle ${item.gko_released?"on":""}" data-action="gko" data-id="${item.id}" data-value="${!item.gko_released}">${item.gko_released?"Liberado":"Pendente"}</button></td>
    <td><button class="toggle ${item.save_posted?"on":""}" data-action="save" data-id="${item.id}" data-value="${!item.save_posted}">${item.save_posted?"Lançado":"Pendente"}</button></td>
    ${["owner","admin"].includes(state.user.role)?`<td><div class="row-actions">${item.has_source_email?`<button data-action="email" data-id="${item.id}" title="Abrir e-mail original">Abrir e-mail</button>`:""}${state.view==="review"?`<button data-action="freight" data-id="${item.id}">É frete</button><button data-action="service" data-id="${item.id}">É serviço</button>`:""}<button data-action="edit" data-id="${item.id}" title="Editar fatura">Editar</button><button data-action="delete" data-id="${item.id}" title="Excluir">Excluir</button></div></td>`:`<td>${item.has_source_email?`<button data-action="email" data-id="${item.id}" title="Abrir e-mail original">Abrir e-mail</button>`:"—"}</td>`}
  </tr>`).join("");
  rows.querySelectorAll("button[data-action]").forEach(button=>button.onclick=()=>invoiceAction(button.dataset.action,Number(button.dataset.id),button.dataset.value==="true"));
}
async function invoiceAction(action,id,value){
  try{
    if(action==="email"){const result=await api(`/api/invoices/${id}/email-link`);if(result.provider==="outlook_desktop"){await api(`/api/invoices/${id}/open-outlook`,{method:"POST"});toast("E-mail aberto no Outlook.");}else window.open(result.url,"_blank","noopener,noreferrer");return}
    if(action==="edit"){editInvoiceForm(id);return}
    if(action==="freight"||action==="service"){await api(`/api/invoices/${id}/classification`,{method:"PATCH",body:JSON.stringify({value:action==="freight"?"FREIGHT":"SERVICE"})});toast("Classificação atualizada.");await loadInvoices();return}
    if(action==="delete"){if(!confirm("Excluir esta fatura?"))return;await api(`/api/invoices/${id}`,{method:"DELETE"});toast("Fatura excluída.")}
    else{await api(`/api/invoices/${id}/${action}`,{method:"PATCH",body:JSON.stringify({value})});toast(action==="gko"?"Status GKO atualizado.":"Status SAVE atualizado.")}
    await Promise.all([loadInvoices(),loadDashboard()])
  }catch(error){toast(error.message,true)}
}
function editInvoiceForm(id){
  const item=state.invoices.find(row=>row.id===id);if(!item)return;
  openModal(`<h2>Editar fatura</h2><p class="lead">Corrija transportadora, número, vencimento e valor.</p><form id="editInvoiceForm" class="form-grid">
    <label>Transportadora<input name="carrier" required value="${esc(item.carrier)}"></label><label>Número da fatura<input name="invoice_number" required value="${esc(item.invoice_number)}"></label>
    <label>Vencimento<input name="due_date" type="date" value="${esc(item.due_date||"")}"></label><label>Valor<input name="amount" type="number" min="0" step="0.01" value="${item.amount??""}"></label>
    <label class="full">Observações<textarea name="notes">${esc(item.notes||"")}</textarea></label><div class="modal-actions full"><button type="button" class="button ghost" data-close>Cancelar</button><button class="button primary">Salvar alterações</button></div></form>`);
  $("modalContent").querySelector("[data-close]").onclick=closeModal;$("editInvoiceForm").onsubmit=async event=>{event.preventDefault();const data=Object.fromEntries(new FormData(event.target));if(!data.due_date)data.due_date=null;if(!data.amount)data.amount=null;try{await api(`/api/invoices/${id}`,{method:"PATCH",body:JSON.stringify(data)});closeModal();toast("Fatura atualizada.");await Promise.all([loadInvoices(),loadDashboard()])}catch(error){toast(error.message,true)}}
}

async function switchView(view){
  if((view==="accounts"||view==="users"||view==="activities")&&!state.user?.role)return;
  if((view==="accounts"||view==="users"||view==="activities")&&!["owner","admin"].includes(state.user.role))return;
  state.view=view;document.querySelectorAll(".nav-item").forEach(button=>button.classList.toggle("active",button.dataset.view===view));document.querySelectorAll(".view").forEach(item=>item.classList.add("hidden"));
  const isInvoices=["pending","completed","services","review"].includes(view);$("invoiceView").classList.toggle("hidden",!isInvoices);$("monthlyView").classList.toggle("hidden",view!=="monthly");$("accountsView").classList.toggle("hidden",view!=="accounts");$("usersView").classList.toggle("hidden",view!=="users");$("activitiesView").classList.toggle("hidden",view!=="activities");
  const titles={pending:["Fretes a pagar","Fretes aguardando GKO e SAVE."],completed:["Fretes concluídos","Fretes com status SAVE lançado."],services:["Serviços a pagar","Cobranças de serviços separadas dos fretes."],review:["Revisar classificação","Escolha se a cobrança é frete ou serviço."],monthly:["Faturas mensais","Consulte valores, volumes e vencimentos por período."],accounts:["Contas de e-mail","Conecte Outlook e Gmail para buscar faturas."],users:["Usuários","Controle o acesso de todos os usuários."],activities:["Atividades","Acompanhe as ações realizadas no sistema."]};$("pageTitle").textContent=titles[view][0];$("pageSubtitle").textContent=titles[view][1];
  document.querySelector(".sidebar").classList.remove("open");
  if(isInvoices){$("invoiceSearch").value="";await Promise.all([loadInvoices(),loadDashboard()])}else if(view==="monthly")await loadMonthly();else if(view==="accounts")await loadAccounts();else if(view==="users")await loadUsers();else await loadActivities();
}

function invoiceForm(){openModal(`<h2>Nova fatura</h2><p class="lead">Cadastre uma fatura manualmente. Duplicatas serão bloqueadas.</p><form id="invoiceForm" class="form-grid">
  <label>Transportadora<input name="carrier" required></label><label>Número da fatura<input name="invoice_number" required></label>
  <label>Vencimento<input name="due_date" type="date"></label><label>Valor<input name="amount" type="number" min="0" step="0.01"></label>
  <label class="full">Observações<textarea name="notes"></textarea></label><div class="modal-actions full"><button type="button" class="button ghost" data-close>Cancelar</button><button class="button primary">Cadastrar fatura</button></div></form>`);
  $("modalContent").querySelector("[data-close]").onclick=closeModal;$("invoiceForm").onsubmit=async event=>{event.preventDefault();const data=Object.fromEntries(new FormData(event.target));if(!data.due_date)delete data.due_date;if(!data.amount)delete data.amount;try{await api("/api/invoices",{method:"POST",body:JSON.stringify(data)});closeModal();toast("Fatura cadastrada.");await Promise.all([loadInvoices(),loadDashboard()])}catch(error){toast(error.message,true)}}
}

async function loadAccounts(){state.accounts=await api("/api/email-accounts");renderAccounts()}
function renderAccounts(){const box=$("accountCards");$("accountsEmpty").classList.toggle("hidden",state.accounts.length>0);box.innerHTML=state.accounts.map(item=>`<article class="account-card"><div class="account-icon">✉</div><div class="account-info"><h3>${esc(item.label)}</h3><p>${esc(item.username)}</p><div class="account-meta"><span class="status-badge ${item.active?"active":"inactive"}">${item.active?"Ativa":"Inativa"}</span><span class="source-badge email">${item.connection_type==="outlook_local"?"Outlook conectado":item.unread_only?"Somente não lidos":"Todos os e-mails"}</span>${item.connection_type==="outlook_local"?`<span class="source-badge email">${item.unread_only?"Somente não lidos":"Todos os e-mails"}</span>`:""}</div>${item.last_error?`<p class="account-error">${esc(item.last_error)}</p>`:""}</div><div class="account-actions"><button class="button ghost" data-test="${item.id}">Testar</button><button class="button ghost" data-edit="${item.id}">Editar</button><button class="button danger" data-delete="${item.id}">Excluir</button></div></article>`).join("");box.querySelectorAll("[data-test]").forEach(b=>b.onclick=()=>testAccount(Number(b.dataset.test)));box.querySelectorAll("[data-edit]").forEach(b=>b.onclick=()=>accountForm(state.accounts.find(a=>a.id===Number(b.dataset.edit))));box.querySelectorAll("[data-delete]").forEach(b=>b.onclick=()=>deleteAccount(Number(b.dataset.delete)))}
function accountForm(item=null){
  const provider=item?.provider||"outlook";
  const configs={
    gmail:{label:"Gmail",host:"imap.gmail.com",port:993,help:"Use o endereço principal da conta Gmail/Google Workspace e uma senha de aplicativo de 16 caracteres. Não use apelido de e-mail."},
    outlook:{label:"Outlook",host:"outlook-desktop",port:993,help:"Conecta à conta já aberta no Outlook clássico deste computador. O FC SERV não solicita nem guarda a senha."},
    outlook_desktop:{label:"Todas as contas do Outlook",host:"outlook-desktop",port:993,help:"Busca em todas as caixas configuradas no Outlook clássico deste computador e não pede senha."},
    other:{label:"Outra conta IMAP",host:"",port:993,help:"Informe os dados IMAP fornecidos pelo seu provedor."}
  };
  const initial=configs[provider]||configs.other;
  openModal(`<h2>${item?"Editar":"Adicionar"} conta</h2><p class="lead">Para Outlook, deixe a conta aberta no Outlook clássico deste computador. Nenhuma senha será solicitada.</p><form id="accountForm" class="form-grid">
    <label>Nome da conta<input name="label" required value="${esc(item?.label||initial.label)}" placeholder="Ex.: Gmail financeiro"></label>
    <label>Provedor<select name="provider" id="providerSelect"><option value="outlook" ${provider==="outlook"?"selected":""}>Outlook / Microsoft 365</option><option value="outlook_desktop" ${provider==="outlook_desktop"?"selected":""}>Todas as contas do Outlook instalado</option><option value="gmail" ${provider==="gmail"?"selected":""}>Gmail / Google Workspace</option><option value="other" ${provider==="other"?"selected":""}>Outro IMAP</option></select></label>
    <label id="imapHostField">Servidor IMAP<input name="imap_host" required value="${esc(item?.imap_host||initial.host)}"></label>
    <label id="imapPortField">Porta<input name="imap_port" type="number" min="1" max="65535" value="${item?.imap_port||initial.port}" required></label>
    <label class="full">E-mail<input name="username" type="email" autocomplete="username" required value="${esc(item?.username||(provider==="outlook_desktop"?"outlook-local@local":""))}" placeholder="seuemail@gmail.com"></label>
    <label class="full" id="passwordField">Senha de aplicativo<input name="password" type="password" autocomplete="new-password" ${item||provider==="outlook"||provider==="outlook_desktop"?"":"required"} placeholder="${item?"Deixe vazio para manter a atual":"Senha de aplicativo"}"></label>
    <div class="full"><small id="providerHelp" class="provider-help">${esc(initial.help)}</small></div>
    <label>Dias para buscar<input name="days_back" type="number" min="1" max="365" value="${item?.days_back||30}"></label>
    <label class="check-row"><input name="unread_only" type="checkbox" ${item?.unread_only!==false?"checked":""}> Buscar somente não lidos</label>
    <label class="check-row"><input name="active" type="checkbox" ${item?.active!==false?"checked":""}> Conta ativa</label>
    <div class="modal-actions full"><button type="button" class="button ghost" data-close>Cancelar</button><button class="button primary">Salvar conta</button></div>
  </form>`);
  const form=$("accountForm");
  const fields=form.elements;
  const configureProvider=(value,replace=false)=>{
    const config=configs[value]||configs.other;
    const localOutlook=value==="outlook"||value==="outlook_desktop";
    const allOutlook=value==="outlook_desktop";
    if(replace){
      fields.namedItem("imap_host").value=config.host;
      fields.namedItem("imap_port").value=config.port;
      if(!item)fields.namedItem("label").value=config.label;
      if(allOutlook)fields.namedItem("username").value="outlook-local@local";
      else if(fields.namedItem("username").value==="outlook-local@local")fields.namedItem("username").value="";
    }
    fields.namedItem("imap_host").readOnly=localOutlook;
    fields.namedItem("imap_port").readOnly=localOutlook;
    fields.namedItem("username").readOnly=allOutlook;
    fields.namedItem("password").disabled=localOutlook;
    fields.namedItem("password").required=!item&&!localOutlook;
    $("imapHostField").hidden=localOutlook;
    $("imapPortField").hidden=localOutlook;
    $("passwordField").hidden=localOutlook;
    $("providerHelp").textContent=config.help;
  };
  $("modalContent").querySelector("[data-close]").onclick=closeModal;
  $("providerSelect").onchange=event=>configureProvider(event.target.value,true);
  configureProvider(provider,provider==="outlook"||provider==="outlook_desktop");
  form.onsubmit=async event=>{event.preventDefault();const data=Object.fromEntries(new FormData(form));if(data.provider==="outlook"||data.provider==="outlook_desktop")data.password="";data.imap_port=Number(data.imap_port);data.days_back=Number(data.days_back);data.unread_only=fields.namedItem("unread_only").checked;data.active=fields.namedItem("active").checked;try{await api(item?`/api/email-accounts/${item.id}`:"/api/email-accounts",{method:item?"PUT":"POST",body:JSON.stringify(data)});closeModal();toast(data.provider==="outlook"||data.provider==="outlook_desktop"?"Conta salva. Clique em Testar para conectar ao Outlook.":"Conta salva com segurança.");await loadAccounts()}catch(error){toast(error.message,true)}}
}
async function testAccount(id){loading(true,"Testando conexão...");try{const result=await api(`/api/email-accounts/${id}/test`,{method:"POST"});toast(result.message)}catch(error){toast(error.message,true)}finally{await loadAccounts();loading(false)}}
async function deleteAccount(id){if(!confirm("Excluir esta conta de e-mail?"))return;try{await api(`/api/email-accounts/${id}`,{method:"DELETE"});toast("Conta excluída.");await loadAccounts()}catch(error){toast(error.message,true)}}

async function loadUsers(){state.users=await api("/api/users");renderUsers()}
function renderUsers(){$("userRows").innerHTML=state.users.map(item=>`<tr><td class="carrier">${esc(item.name)}</td><td>${esc(item.username)}</td><td><span class="role-badge ${item.role}">${item.role==="owner"?"Proprietário":item.role==="admin"?"Administrador":"Usuário"}</span></td><td><span class="status-badge ${item.active?"active":"inactive"}">${item.active?"Ativo":"Inativo"}</span></td><td>${item.role==="owner"?'<button class="button ghost" disabled>Protegido</button>':`<button class="button ${item.active?"danger":"success"}" data-user="${item.id}" data-active="${!item.active}">${item.active?"Desativar":"Ativar"}</button>`}</td></tr>`).join("");$("userRows").querySelectorAll("[data-user]").forEach(button=>button.onclick=()=>toggleUser(Number(button.dataset.user),button.dataset.active==="true"))}
function userForm(){openModal(`<h2>Novo usuário</h2><p class="lead">A nova conta terá acesso de usuário comum. Somente o proprietário do servidor é administrador.</p><form id="userForm" class="form-grid"><label>Nome<input name="name" required></label><label>Usuário<input name="username" required minlength="3"></label><label class="full">Senha temporária<input name="password" type="password" required minlength="8"></label><div class="modal-actions full"><button type="button" class="button ghost" data-close>Cancelar</button><button class="button primary">Criar usuário</button></div></form>`);$("modalContent").querySelector("[data-close]").onclick=closeModal;$("userForm").onsubmit=async event=>{event.preventDefault();try{await api("/api/users",{method:"POST",body:JSON.stringify(Object.fromEntries(new FormData(event.target)))});closeModal();toast("Usuário comum criado.");await loadUsers()}catch(error){toast(error.message,true)}}}
async function toggleUser(id,value){try{await api(`/api/users/${id}/active`,{method:"PATCH",body:JSON.stringify({value})});toast("Status do usuário atualizado.");await loadUsers()}catch(error){toast(error.message,true)}}

async function excelManager(){
  try{
    const status=await api("/api/excel/status");
    openModal(`<h2>Gerenciar planilha Excel</h2><p class="lead">Existem <strong>${status.imported_invoices}</strong> fatura(s) importada(s) do Excel.</p><div class="excel-options">
      <section><div><h3>Adicionar ou atualizar</h3><p>Importa somente faturas novas e mantém tudo que já está cadastrado.</p></div><button type="button" class="button primary" data-excel-add>Escolher planilha</button></section>
      <section><div><h3>Substituir planilha</h3><p>Remove as faturas de origem Excel e importa a nova planilha. Faturas manuais e de e-mail são preservadas.</p></div><button type="button" class="button ghost" data-excel-replace>Substituir</button></section>
      <section class="danger-option"><div><h3>Remover dados do Excel</h3><p>Remove somente as faturas importadas do Excel. Um backup é criado antes da remoção.</p></div><button type="button" class="button danger" data-excel-remove>Remover</button></section>
    </div><div class="modal-actions"><button type="button" class="button ghost" data-close>Fechar</button></div>`);
    $("modalContent").querySelector("[data-close]").onclick=closeModal;
    $("modalContent").querySelector("[data-excel-add]").onclick=()=>{closeModal();$("excelInput").click()};
    $("modalContent").querySelector("[data-excel-replace]").onclick=()=>{closeModal();$("excelReplaceInput").click()};
    $("modalContent").querySelector("[data-excel-remove]").onclick=()=>removeExcelData(status.imported_invoices);
  }catch(error){toast(error.message,true)}
}
async function handleExcelFile(event,replace=false){
  const file=event.target.files[0];
  if(!file)return;
  if(replace&&!confirm("Substituir os dados atuais do Excel por esta planilha? As faturas manuais e de e-mail serão preservadas.")){event.target.value="";return}
  const form=new FormData();form.append("file",file);loading(true,replace?"Substituindo a planilha...":"Importando e filtrando a planilha...");
  try{
    const result=await api(replace?"/api/excel/replace":"/api/excel/import",{method:"POST",body:form,timeout:300000});
    toast(replace?`Planilha substituída: ${result.removed} removida(s), ${result.inserted} importada(s) — ${result.freights||0} frete(s) e ${result.services||0} serviço(s).`:`${result.inserted} importada(s) — ${result.freights||0} frete(s), ${result.services||0} serviço(s), ${result.duplicates} duplicata(s) e ${result.ignored||0} linha(s) ignorada(s).`);
    await refreshCurrentData();
  }catch(error){toast(error.message,true)}finally{event.target.value="";loading(false)}
}
async function removeExcelData(count){
  if(!count){closeModal();toast("Não há faturas importadas do Excel para remover.");return}
  if(!confirm(`Remover ${count} fatura(s) importada(s) do Excel? Um backup será criado e as faturas manuais e de e-mail serão preservadas.`))return;
  loading(true,"Criando backup e removendo dados do Excel...");
  try{const result=await api("/api/excel/imported",{method:"DELETE"});closeModal();toast(`${result.removed} fatura(s) do Excel removida(s).`);await refreshCurrentData()}catch(error){toast(error.message,true)}finally{loading(false)}
}

async function loadActivities(){state.activities=await api("/api/audit-logs?limit=500");renderActivities()}
function renderActivities(){$("activityRows").innerHTML=state.activities.map(item=>`<tr><td>${brDateTime(item.created_at)}</td><td class="carrier">${esc(item.username)}</td><td>${esc(item.action)}</td><td><span class="status-badge ${item.status_code<400?"active":"inactive"}">${item.status_code}</span></td><td>${esc(item.ip_address||"—")}</td></tr>`).join("");$("activitiesEmpty").classList.toggle("hidden",state.activities.length>0)}
function brDateTime(value){return value?new Date(`${value}Z`).toLocaleString("pt-BR"):"—"}

$("setupForm").onsubmit=async event=>{event.preventDefault();try{const result=await api("/api/setup",{method:"POST",body:JSON.stringify(Object.fromEntries(new FormData(event.target)))});showApp(result.user);toast("Administrador criado com sucesso.")}catch(error){toast(error.message,true)}};
$("loginForm").onsubmit=async event=>{event.preventDefault();try{const result=await api("/api/login",{method:"POST",body:JSON.stringify(Object.fromEntries(new FormData(event.target)))});showApp(result.user)}catch(error){toast(error.message,true)}};
$("logoutBtn").onclick=async()=>{await api("/api/logout",{method:"POST"});state.user=null;showAuth(false)};
document.querySelectorAll(".nav-item").forEach(button=>button.onclick=()=>switchView(button.dataset.view));$("menuBtn").onclick=()=>document.querySelector(".sidebar").classList.toggle("open");$("newInvoiceBtn").onclick=invoiceForm;$("newAccountBtn").onclick=()=>accountForm();$("newUserBtn").onclick=userForm;$("excelManageBtn").onclick=excelManager;$("modalClose").onclick=closeModal;$("modal").onclick=event=>{if(event.target===$("modal"))closeModal()};
$("invoiceSearch").oninput=()=>{clearTimeout(state.searchTimer);state.searchTimer=setTimeout(loadInvoices,300)};
$("syncBtn").onclick=async()=>{loading(true,"Classificando fretes e serviços no Outlook...");try{const result=await api("/api/email/sync",{method:"POST"});const errors=result.errors?.length?` Erro: ${result.errors.join(" | ")}`:"";toast(`${result.inserted} nova(s) cobrança(s), ${result.duplicates} duplicata(s).${errors}`,Boolean(result.errors?.length));await refreshCurrentData()}catch(error){toast(error.message,true)}finally{loading(false)}};
$("excelInput").onchange=event=>handleExcelFile(event,false);
$("excelReplaceInput").onchange=event=>handleExcelFile(event,true);


function applyExcelFilters(){
  const get=name=>document.querySelector(`[data-filter="${name}"]`)?.value.trim().toLowerCase()||"";
  const carrier=get("carrier"),invoice=get("invoice"),due=get("due"),amount=get("amount"),source=get("source"),gko=get("gko"),save=get("save");
  state.filteredInvoices=state.invoices.filter(x=>(!carrier||x.carrier.toLowerCase().includes(carrier))&&(!invoice||x.invoice_number.toLowerCase().includes(invoice))&&(!due||x.due_date===due)&&(!amount||String(x.amount??"").includes(amount.replace(",",".")))&&(!source||x.source===source)&&(!gko||String(x.gko_released)===gko)&&(!save||String(x.save_posted)===save));
  renderInvoices();
}
document.querySelectorAll("[data-filter]").forEach(el=>el.addEventListener("input",applyExcelFilters));
$("clearFilters").onclick=()=>{document.querySelectorAll("[data-filter]").forEach(el=>el.value="");applyExcelFilters()};

const monthNames=["Janeiro","Fevereiro","Março","Abril","Maio","Junho","Julho","Agosto","Setembro","Outubro","Novembro","Dezembro"];
$("monthlyMonth").innerHTML=monthNames.map((m,i)=>`<option value="${i+1}">${m}</option>`).join("");
$("monthlyMonth").value=new Date().getMonth()+1;$("monthlyYear").value=new Date().getFullYear();
async function loadMonthly(){const q=new URLSearchParams({month:$("monthlyMonth").value,year:$("monthlyYear").value,carrier:$("monthlyCarrier").value,status:$("monthlyStatus").value});const data=await api(`/api/invoices/monthly-summary?${q}`);$("monthTotal").textContent=money(data.total_amount);$("monthCount").textContent=data.count;$("monthCompleted").textContent=data.completed;$("monthOverdue").textContent=data.overdue;$("monthlyRows").innerHTML=data.invoices.map(item=>`<tr><td>${brDate(item.inclusion_date)}</td><td class="carrier">${esc(item.carrier)}</td><td><button class="invoice-link" onclick="invoiceAction('email',${item.id},false)">${esc(item.invoice_number)}</button></td><td>${brDate(item.due_date)}</td><td class="money">${money(item.amount)}</td><td>${item.gko_released?"Liberado":"Pendente"}</td><td>${item.save_posted?"Lançado":"Pendente"}</td><td><button onclick="editInvoiceForm(${item.id})">Editar</button></td></tr>`).join("");state.invoices=data.invoices;}
$("monthlyApply").onclick=loadMonthly;

const loginModeBtn=$("loginModeBtn");
if(loginModeBtn){loginModeBtn.onclick=()=>{showAuth(false);setTimeout(()=>$("loginForm")?.querySelector("input[name=username]")?.focus(),0)}}

bootstrap();
