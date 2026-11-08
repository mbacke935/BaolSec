import subprocess
NAVY="#1F3864"
def tbl(name, cols, head="#DCE6F2", border=NAVY):
    rows=[f'<tr><td colspan="3" bgcolor="{head}" port="h"><b>{name}</b></td></tr>']
    for c in cols:
        n,ty,k = (c+("",))[:3] if len(c)==2 else c
        key = {"PK":"<b>PK</b>","FK":"FK","PK,FK":"<b>PK</b>,FK","UQ":"UQ","FK,UQ":"FK,UQ","PK,FK,UQ":"<b>PK</b>,FK,UQ"}.get(k,k)
        nm = f"<u>{n}</u>" if "PK" in k else n
        rows.append(f'<tr><td align="left" port="{n}">{nm}</td><td align="left"><font color="#546E7A">{ty}</font></td><td align="left">{('<font color="#1565C0">'+key+'</font>') if key else ' '}</td></tr>')
    return f'<<table border="1" cellborder="0" cellspacing="0" cellpadding="3" color="{border}">{"".join(rows)}</table>>'
def ext(name):
    return f'<<table border="1" cellborder="0" cellspacing="0" cellpadding="4" color="#90A4AE" style="dashed"><tr><td bgcolor="#ECEFF1"><font color="#546E7A">{name}</font></td></tr></table>>'
def render(fname, title, tables, externals, edges, rankdir="LR", extra=""):
    out=[f'digraph G {{ graph [rankdir={rankdir}, fontname="DejaVu Sans", labelloc=t, label=<<b>{title}</b><br/> >, fontsize=20, dpi=200, nodesep=0.4, ranksep=0.9, pad=0.3]; node [shape=plain, fontname="DejaVu Sans", fontsize=11]; edge [color="#37474F", arrowsize=0.8, fontname="DejaVu Sans", fontsize=9];']
    for n,cols in tables: out.append(f'"{n}" [label={tbl(n,cols)}];')
    for n in externals: out.append(f'"{n}" [label={ext(n)}];')
    for a,b,lab in edges:
        st = ', style=dashed, color="#78909C"' if b in externals or a in externals else ''
        out.append(f'"{a}" -> "{b}" [label="{lab}", arrowhead=normal{st}];')
    out.append(LEGEND)
    out.append(extra+"}")
    open(fname+".dot","w").write("\n".join(out))
    subprocess.run(["dot","-Tpng",fname+".dot","-o",fname+".png"],check=True)

TS="timestamptz"
LEGEND = ('LEG [label=<<table border="1" cellborder="1" cellspacing="0" cellpadding="4" color="#90A4AE">'
  '<tr><td colspan="2" bgcolor="#ECEFF1"><b>Légende</b></td></tr>'
  '<tr><td>trait plein, pointe pleine</td><td align="left">clé étrangère dans le même schéma (de la table qui référence vers la table référencée)</td></tr>'
  '<tr><td>tirets gris</td><td align="left">clé étrangère vers une table d\'un autre schéma, lue sans droit d\'écriture</td></tr>'
  '<tr><td>cadre en tirets</td><td align="left">table d\'un autre schéma</td></tr>'
  '<tr><td><u>souligné</u> · PK · FK · UQ</td><td align="left">clé primaire · clé étrangère · contrainte d\'unicité</td></tr>'
  '</table>>];')
render("mld_acces","MLD — Schéma acces (écrivain : API)",[
 ("roles",[("id","uuid","PK"),("name","text","UQ"),("description","text","")]),
 ("permissions",[("id","uuid","PK"),("code","text","UQ"),("description","text","")]),
 ("role_permissions",[("role_id","uuid","PK,FK"),("permission_id","uuid","PK,FK")]),
 ("users",[("id","uuid","PK"),("username","text","UQ"),("email","text","UQ"),("password_hash","text",""),("role_id","uuid","FK"),("is_active","boolean",""),("failed_attempts","integer",""),("locked_until",TS,""),("last_login_at",TS,""),("created_at / updated_at",TS,"")]),
 ("user_sessions",[("id","uuid","PK"),("user_id","uuid","FK"),("refresh_token_hash","text",""),("issued_at",TS,""),("expires_at",TS,""),("revoked_at",TS,"")]),
 ("audit_log",[("id","bigint","PK"),("occurred_at",TS,""),("actor_id","uuid","FK"),("actor_username","text",""),("action","text",""),("target_type / target_id","text",""),("outcome","enum",""),("details","jsonb",""),("client_ip","inet","")]),
],[],[("users","roles","role_id"),("role_permissions","roles","role_id"),("role_permissions","permissions","permission_id"),("user_sessions","users","user_id"),("audit_log","users","actor_id (SET NULL)")])

render("mld_config","MLD — Schéma config (écrivain : API)",[
 ("sources",[("id","uuid","PK"),("name","text","UQ"),("source_type","enum",""),("transport","enum",""),("ingestion_mode","enum",""),("host","text",""),("criticality","enum",""),("silence_threshold_s","integer",""),("expected_min_events_per_h","integer",""),("is_enabled","boolean",""),("created_at / updated_at",TS,"")]),
 ("source_credentials",[("id","uuid","PK"),("source_id","uuid","FK"),("credential_type","enum",""),("secret_hash","text",""),("cert_fingerprint","text","UQ"),("created_at",TS,""),("expires_at",TS,""),("revoked_at",TS,"")]),
 ("rules",[("id","uuid","PK"),("name","text","UQ"),("description","text",""),("rule_type","enum",""),("severity","enum",""),("is_enabled","boolean",""),("current_version","integer",""),("created_by","uuid","FK"),("created_at / updated_at",TS,"")]),
 ("rule_versions",[("rule_id","uuid","PK,FK"),("version","integer","PK"),("definition_yaml","text",""),("checksum","text",""),("created_by","uuid","FK"),("created_at",TS,"")]),
 ("rule_requirements",[("id","uuid","PK"),("rule_id","uuid","FK"),("source_type","enum",""),("source_id","uuid","FK"),("required_fields","text[]","")]),
 ("settings",[("key","text","PK"),("value","jsonb",""),("updated_by","uuid","FK"),("updated_at",TS,"")]),
],["acces.users"],[("source_credentials","sources","source_id"),("rule_versions","rules","rule_id"),("rule_requirements","rules","rule_id"),("rule_requirements","sources","source_id (nul possible)"),("rules","acces.users","created_by"),("rule_versions","acces.users","created_by"),("settings","acces.users","updated_by")])

render("mld_incidents","MLD — Schéma incidents (écrivain : service Incidents)",[
 ("alert_state",[("alert_id","text","PK"),("rule_id","uuid","FK"),("severity","enum",""),("triggered_at",TS,""),("status","enum",""),("assigned_to","uuid","FK"),("status_changed_at",TS,""),("created_at",TS,"")]),
 ("incidents",[("id","uuid","PK"),("title","text",""),("status","enum",""),("severity","enum",""),("correlation_context","jsonb",""),("opened_at",TS,""),("last_activity_at",TS,""),("closed_at",TS,""),("assigned_to","uuid","FK")]),
 ("incident_alerts",[("incident_id","uuid","PK,FK"),("alert_id","text","PK,FK,UQ"),("attached_at",TS,""),("criteria","jsonb","")]),
 ("incident_timeline",[("id","bigint","PK"),("incident_id","uuid","FK"),("occurred_at",TS,""),("recorded_at",TS,""),("entry_type","enum",""),("alert_id","text","FK"),("event_id","text",""),("summary","text",""),("justification","jsonb",""),("actor_id","uuid","FK")]),
 ("incident_comments",[("id","uuid","PK"),("incident_id","uuid","FK"),("author_id","uuid","FK"),("body","text",""),("created_at",TS,"")]),
 ("incident_commands",[("command_id","uuid","PK"),("command_type","enum",""),("incident_id","uuid","FK"),("alert_id","text","FK"),("issued_by","uuid","FK"),("payload","jsonb",""),("result","enum",""),("error","text",""),("created_at",TS,""),("completed_at",TS,"")]),
],["config.rules","acces.users"],[("incident_alerts","incidents","incident_id"),("incident_alerts","alert_state","alert_id (UNIQUE)"),("incident_timeline","incidents","incident_id"),("incident_timeline","alert_state","alert_id"),("incident_comments","incidents","incident_id"),("incident_commands","incidents","incident_id"),("incident_commands","alert_state","alert_id"),("alert_state","config.rules","rule_id"),("alert_state","acces.users","assigned_to"),("incidents","acces.users","assigned_to"),("incident_comments","acces.users","author_id"),("incident_commands","acces.users","issued_by"),("incident_timeline","acces.users","actor_id")])

render("mld_couverture","MLD — Schéma couverture (écrivain : service Couverture)",[
 ("coverage_state",[("source_id","uuid","PK,FK"),("state","enum",""),("state_since",TS,""),("last_received_at",TS,""),("last_normalized_at",TS,""),("last_evaluated_at",TS,"")]),
 ("coverage_state_history",[("id","bigint","PK"),("source_id","uuid","FK"),("from_state","enum",""),("to_state","enum",""),("reason","text",""),("changed_at",TS,"")]),
 ("coverage_stats",[("source_id","uuid","PK,FK"),("bucket_start",TS,"PK"),("received_count","bigint",""),("normalized_count","bigint",""),("rejected_count","bigint",""),("error_count","bigint","")]),
 ("coverage_affected_rules",[("source_id","uuid","PK,FK"),("rule_id","uuid","PK,FK"),("since",TS,"PK"),("cause","enum",""),("resolved_at",TS,"")]),
 ("coverage_batches",[("consumer","text","PK"),("batch_id","bigint","PK"),("committed_at",TS,""),("stream_seqs","bigint[]","")]),
],["config.sources","config.rules"],[("coverage_state","config.sources","source_id"),("coverage_state_history","config.sources","source_id"),("coverage_stats","config.sources","source_id"),("coverage_affected_rules","config.sources","source_id"),("coverage_affected_rules","config.rules","rule_id")])
