(function(){
  "use strict";
  var chat = document.getElementById('chat');
  var input = document.getElementById('input');
  var sendBtn = document.getElementById('send');
  var statusBox = document.getElementById('status');
  var history = [];
  var sending = false;

  // ---- 会话持久化（M5 工程化）：刷新/重启后可恢复多轮对话 ----
  var sessionId = localStorage.getItem('netops_sid');
  if(!sessionId){
    sessionId = 's-' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 8);
    localStorage.setItem('netops_sid', sessionId);
  }

  // ---- 认证状态 ----
  var authToken = localStorage.getItem('netops_token') || '';
  var authEnabled = false;
  var authbar = document.getElementById('authbar');
  var authtoken = document.getElementById('authtoken');
  var authbtn = document.getElementById('authbtn');
  var rolebadge = document.getElementById('rolebadge');

  // 当前 SSE 流的 AbortController：切换/删除会话时中止旧流，防止旧响应继续写 DOM
  var activeController = null;
  function abortStream(){
    if(activeController){ try{ activeController.abort(); }catch(e){} activeController = null; }
  }

  function apiFetch(url, opts){
    opts = opts || {};
    var h = Object.assign({}, opts.headers || {});
    if(authToken) h['Authorization'] = 'Bearer ' + authToken;
    opts.headers = h;
    return fetch(url, opts);
  }
  function renderAuth(me){
    authEnabled = !!me.auth_enabled;
    if(!authEnabled){
      authbar.style.display = 'none';
      return;
    }
    authbar.style.display = 'flex';
    // 角色裁剪：仿真场景切换仅 admin 可用
    if(me.authenticated && me.role === 'admin'){ simbar.style.display = 'flex'; }
    else { simbar.style.display = 'none'; }
    if(me.authenticated && me.role){
      authtoken.style.display = 'none';
      authbtn.textContent = '退出';
      rolebadge.textContent = '角色：' + me.role;
      rolebadge.className = me.role;
      rolebadge.style.display = 'inline-block';
    }else{
      authtoken.style.display = 'inline-block';
      authbtn.textContent = '登录';
      rolebadge.textContent = '';
      rolebadge.style.display = 'none';
    }
  }
  authbtn.addEventListener('click', function(){
    if(authToken && authbtn.textContent === '退出'){
      authToken = '';
      localStorage.removeItem('netops_token');
      authbar.style.display = 'none';
      authtoken.style.display = 'inline-block';
      authbtn.textContent = '登录';
      rolebadge.style.display = 'none';
      setStatus('已退出登录（未认证为 viewer）');
      return;
    }
    var tok = authtoken.value.trim();
    if(!tok){ alert('请输入访问令牌'); return; }
    apiFetch('/api/auth/me', {headers:{'Authorization':'Bearer ' + tok}})
      .then(function(r){ return r.json(); })
      .then(function(me){
        if(me.authenticated){
          authToken = tok;
          localStorage.setItem('netops_token', tok);
          renderAuth(me);
          setStatus('已登录 · 角色 ' + me.role);
        }else{
          alert('令牌无效或未配置对应角色');
        }
      })
      .catch(function(e){ alert('登录失败：' + e.message); });
  });

  function el(tag, cls, text){
    var n = document.createElement(tag);
    if(cls) n.className = cls;
    if(text !== undefined) n.textContent = text;
    return n;
  }
  function appendMsg(role, text, isErr){
    var row = el('div', 'msg ' + (role === 'user' ? 'user' : 'bot'));
    row.appendChild(el('div', 'avatar', role === 'user' ? '我' : 'AI'));
    var b = el('div', 'bubble' + (isErr ? ' err' : ''), text);
    row.appendChild(b);
    chat.appendChild(row);
    chat.scrollTop = chat.scrollHeight;
    return b;
  }
  function setStatus(html){
    statusBox.innerHTML = '<span class="dot"></span>' + html;
  }

  function addSourcesFooter(bubble, sources){
    var f = document.createElement('div');
    f.style.cssText = 'margin-top:10px;padding-top:8px;border-top:1px solid rgba(53,195,216,.25);font-size:12px;color:#9FB4BD;';
    f.textContent = '📎 参考来源：' + sources.map(function(s){ return s.source + ' (' + Math.round((s.score||0)*100) + '%)'; }).join(' · ');
    bubble.appendChild(f);
  }

  function parseSSE(res){
    var reader = res.body.getReader();
    var decoder = new TextDecoder();
    var buf = '';
    return (async function(){
      var bubble = null, acc = '', curSources = null, traceBox = null, thinkLine = null;
      function ensureTrace(){
        if(traceBox) return traceBox;
        var row = el('div', 'msg bot');
        row.appendChild(el('div', 'avatar', 'AI'));
        var box = el('div', 'bubble tracebox');
        box.appendChild(el('div', 'tracetitle', '🔧 工具调用过程'));
        row.appendChild(box);
        chat.appendChild(row);
        chat.scrollTop = chat.scrollHeight;
        traceBox = box;
        return box;
      }
      while(true){
        var r = await reader.read();
        if(r.done) break;
        buf += decoder.decode(r.value, {stream:true});
        var idx;
        while((idx = buf.indexOf('\n\n')) !== -1){
          var block = buf.slice(0, idx);
          buf = buf.slice(idx + 2);
          block.split('\n').forEach(function(line){
            if(!line.startsWith('data: ')) return;
            var data;
            try{ data = JSON.parse(line.slice(6)); }catch(e){ return; }
            if(data.type === 'delta'){
              if(!bubble){ bubble = appendMsg('assistant', ''); }
              if(thinkLine && thinkLine.parentNode){ thinkLine.parentNode.removeChild(thinkLine); }
              thinkLine = null;
              acc += data.content;
              bubble.textContent = acc;
              chat.scrollTop = chat.scrollHeight;
            }else if(data.type === 'sources'){
              curSources = data.sources || [];
            }else if(data.type === 'tool'){
              var box = ensureTrace();
              var line = el('div', 'traceline');
              var mark = data.ok ? '<span class="ok">✓</span>' : '<span class="no">✗</span>';
              var args = data.args ? esc(JSON.stringify(data.args)) : '';
              var result = esc((data.result || '').replace(/\n/g, ' ').slice(0, 140));
              line.innerHTML = mark + ' <span class="tk">' + (data.tool||'') + '</span> ' + args + '<br>' + result;
              box.appendChild(line);
              chat.scrollTop = chat.scrollHeight;
            }else if(data.type === 'thinking'){
              var txt = (data.text||'').replace(/</g,'&lt;');
              if(data.step){
                // Agent 步骤思考（保留原有样式）
                var box = ensureTrace();
                var line = el('div', 'traceline');
                line.style.cssText = 'opacity:.75;font-size:12px;color:#8aa;white-space:pre-wrap;';
                line.innerHTML = '💭 <span style="color:#6aa">第' + (data.step||'') + '步思考</span><br>' + txt;
                box.appendChild(line);
              }else{
                // 普通问答的"思考中"占位（收到回答即消失）
                thinkLine = el('div', 'traceline thinking-anim');
                thinkLine.innerHTML = '💭 <span style="color:#6aa">' + txt + '</span>';
                ensureTrace().appendChild(thinkLine);
              }
              chat.scrollTop = chat.scrollHeight;
            }else if(data.type === 'done'){
              if(!bubble){ bubble = appendMsg('assistant', ''); }
              if(curSources && curSources.length){ addSourcesFooter(bubble, curSources); }
              history.push({role:'assistant', content: acc || '(空回复)'});
            }else if(data.type === 'error'){
              if(!bubble){ bubble = appendMsg('assistant', '', true); }
              bubble.className = 'bubble err';
              bubble.textContent = data.message || '未知错误';
              history.push({role:'assistant', content:'[错误] ' + (data.message||'')});
            }
          });
        }
      }
      if(!bubble){ appendMsg('assistant', '(无输出)'); }
    })();
  }

  async function send(){
    if(sending) return;
    var text = input.value.trim();
    if(!text) return;
    input.value = '';
    input.style.height = 'auto';
    appendMsg('user', text);
    history.push({role:'user', content:text});
    refreshSessions();
    sending = true;
    sendBtn.disabled = true;
    activeController = new AbortController();
    try{
      var res = await apiFetch('/api/chat', {
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body: JSON.stringify({message:text, history: history.slice(0, -1), session_id: sessionId}),
        signal: activeController.signal
      });
      if(!res.ok || !res.body){ throw new Error('请求失败 HTTP ' + res.status + (res.status === 403 ? '（权限不足）' : '')); }
      await parseSSE(res);
    }catch(e){
      if(e.name === 'AbortError'){ /* 用户切换/清空会话导致流被中止：静默 */ }
      else appendMsg('assistant', '连接失败：' + e.message, true);
    }finally{
      sending = false;
      sendBtn.disabled = false;
      activeController = null;
      input.focus();
    }
  }

  function autoResize(){
    input.style.height = 'auto';
    input.style.height = Math.min(input.scrollHeight, 160) + 'px';
  }

  input.addEventListener('input', autoResize);
  input.addEventListener('keydown', function(e){
    if(e.key === 'Enter' && !e.shiftKey){ e.preventDefault(); send(); }
  });
  sendBtn.addEventListener('click', send);

  function addChips(){
    if(history.length > 0) return;
    var ph = el('div', 'placeholder');
    ph.innerHTML = '<div class="big">网络运维智能助手</div>输入故障现象，助手将检索知识库并给出排查建议。';
    var chips = el('div', 'chips');
    ['端口 flapping 怎么排查？','如何查看交换机接口收发光功率？','OSPF 邻居状态一直 DOWN 怎么办？','从 core-sw-1 检查到 10.0.1.2 的连通性并排查 OSPF 邻居问题'].forEach(function(t){
      var c = el('span', 'chip', t);
      c.addEventListener('click', function(){ input.value = t; send(); });
      chips.appendChild(c);
    });
    ph.appendChild(chips);
    chat.appendChild(ph);
  }

  // ---- 仿真故障场景切换 ----
  var SCENARIO_QUESTIONS = {
    flapping: '从 core-sw-1 检查到 10.0.1.2 的连通性并排查 OSPF 邻居问题',
    stp_loop: 'core-sw-1 的 CPU 占用率很高，接口 GE0/0/1 和 GE0/0/2 收发速率异常，网络时通时断，帮我排查是否环路',
    arp_poison: '核心交换机上 10.0.1.2 经常 ping 不通，接口都是 up 的，帮我排查 ARP 问题',
    bgp_flap: 'core-rtr-1 的 BGP 邻居 10.0.1.1 一直处于 Active 状态，帮我排查原因',
    acl_deny: '从 core-sw-1 ping 10.0.1.2 全部超时但接口是 up 的，怀疑被 ACL 拦截，帮我确认并给出处置',
    dhcp_failure: '终端区突然大面积拿不到 IP 地址，接口都是 up 的，帮我排查 DHCP 问题并给出处置',
    ospf_neighbor: 'core-rtr-1 的 OSPF 邻居 1.1.1.1 一直卡在 ExStart 状态，帮我定位原因并给出处置',
    link_congestion: '监控显示 core-sw-1 上联 GE0/0/1 利用率接近打满，业务时延变高还间歇丢包，帮我排查根因'
  };
  var simbar = document.getElementById('simbar');
  var simselect = document.getElementById('simselect');
  var simswitch = document.getElementById('simswitch');
  var simtip = document.getElementById('simtip');
  function setSimTip(name){
    simtip.textContent = SCENARIO_QUESTIONS[name] ? '示例问题：' + SCENARIO_QUESTIONS[name] : '';
  }
  simswitch.addEventListener('click', function(){
    var name = simselect.value;
    apiFetch('/api/sim/scenario', {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({scenario: name})
    }).then(function(r){ return r.json(); }).then(function(d){
      if(d.ok){ setSimTip(d.scenario); simselect.value = d.scenario; }
      else{ alert('切换失败：' + (d.message || '未知错误')); }
    }).catch(function(e){ alert('切换失败：' + e.message); });
  });

  // ---- 排障报告导出（M6 产品化） ----
  document.getElementById('reportbtn').addEventListener('click', function(){
    apiFetch('/api/report/' + encodeURIComponent(sessionId)).then(function(r){ return r.json(); }).then(function(d){
      if(d.ok){
        setStatus('报告已生成，正在打开…');
        location.href = d.report_url;
      }else{ alert('导出失败：' + (d.message || '未知错误')); }
    }).catch(function(e){ alert('导出失败：' + e.message); });
  });

  apiFetch('/api/health').then(function(r){ return r.json(); }).then(function(d){
    var model = d.model || '-';
    if(d.mock){ setStatus('模拟模式（未配置 API Key） · 模型 ' + model + ' · <span class="mock">LLM_MOCK=true</span>'); }
    else{ setStatus('智谱 GLM 已连接 · 模型 ' + model + (d.key_configured ? '' : ' · Key 未配置')); }
    if(d.device_mode === 'simulate' && d.sim_scenario){
      simbar.style.display = 'flex';
      simselect.value = d.sim_scenario;
      setSimTip(d.sim_scenario);
    }
    addChips();
    // 会话恢复：读取后端落盘的历史消息
    apiFetch('/api/session/' + encodeURIComponent(sessionId)).then(function(r){ return r.json(); }).then(function(d){
      if(d && d.ok && d.messages && d.messages.length){
        var ph = chat.querySelector('.placeholder');
        if(ph) ph.remove();
        d.messages.forEach(function(m){
          history.push({role:m.role, content:m.content});
          if(m.role === 'assistant') appendMsg(m.role, m.content || '(空回复)');
          else appendMsg(m.role, m.content);
        });
      }
    }).catch(function(){});
    // 认证状态与角色裁剪
    apiFetch('/api/auth/me').then(function(r){ return r.json(); }).then(function(me){
      renderAuth(me);
    }).catch(function(){});
  }).catch(function(){ setStatus('后端未连接（请先启动 uvicorn）'); });

  // ================= FRR 真实拓扑页（方案 B） =================
  var mainBox = document.getElementById('main');
  var chatBox = document.getElementById('chat');
  var topoBox = document.getElementById('topo');
  var svgBox = document.getElementById('topo-svg-box');
  var topoCards = document.getElementById('topoCards');
  var topoBanner = document.getElementById('topoBanner');
  var autoRefresh = document.getElementById('autoRefresh');
  var topoRefresh = document.getElementById('topoRefresh');

  // ---- 设备几何（SVG viewBox 900x280） ----
  var TOPO_LAYOUT = [
    {name:'frr1', x:40,  y:100, w:210, h:100, label:'frr1 · OSPF', role:'AS 内部路由器', right:'OSPF → frr2', rightX:250, rightY:150},
    {name:'frr2', x:345, y:100, w:210, h:100, label:'frr2 · OSPF+eBGP', role:'AS 65002 边界', left:'← OSPF', right:'eBGP → frr3', rightX:555, rightY:150},
    {name:'frr3', x:650, y:100, w:210, h:100, label:'frr3 · eBGP', role:'AS 65003 边界', left:'← eBGP', rightX:0, rightY:0}
  ];
  var TOPO_LINKS = [
    {x1:250, y1:150, x2:345, y2:150, label:'OSPF · Area 0', key:'12'},
    {x1:555, y1:150, x2:650, y2:150, label:'eBGP · 65002↔65003', key:'23'}
  ];

  function nodeHealth(dev){
    var h = dev.parsed && dev.parsed.healthy;
    var faults = dev.active_faults || {};
    var faultNames = Object.keys(faults);
    if(faultNames.length){
      // link_down / bgp_neighbor_down → 红（链路真断）；ospf_cost → 黄（路由劣化）
      var hardDown = faultNames.some(function(f){ return f === 'link_down' || f === 'bgp_neighbor_down'; });
      return hardDown ? 'bad' : 'warn';
    }
    return h === true ? 'ok' : (h === false ? 'bad' : 'unk');
  }
  function faultBadge(dev){
    var faults = dev.active_faults || {};
    var map = {link_down:'链路中断', ospf_cost:'路由劣化', bgp_neighbor_down:'BGP 会话中断'};
    return Object.keys(faults).map(function(f){ return '⚠ ' + (map[f] || f); }).join(' · ');
  }
  function linkHealth(devs, key){
    // OSPF 链路健康看 frr1/frr2；eBGP 链路看 frr2/frr3
    var names = key === '12' ? ['frr1','frr2'] : ['frr2','frr3'];
    var states = names.map(function(n){ return nodeHealth(devs[n] || {}); });
    if(states.indexOf('bad') !== -1) return 'bad';
    if(states.indexOf('ok') === -1) return 'unk';
    return 'ok';
  }

  function renderTopoSvg(devs){
    var names = Object.keys(devs);
    if(!names.length){
      svgBox.innerHTML = '<div class="topo-hint">无在跑的 FRR 容器（请启动 Docker 并 docker compose up -d）</div>';
      return;
    }
    // 动态布局：N 个节点横向等距排列
    var n = names.length;
    var boxW = 260, boxH = 120, gap = (900 - n*boxW) / (n+1);
    var nodes = names.map(function(name, i){
      return {name: name, x: gap + i*(boxW+gap), y: 80, w: boxW, h: boxH};
    });
    var parts = [];
    parts.push('<svg viewBox="0 0 900 280" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="FRR 真实路由拓扑图">');
    // 链路：相邻节点连虚线
    for(var i=0;i<nodes.length-1;i++){
      var a=nodes[i], b=nodes[i+1];
      var da=devs[a.name], db=devs[b.name];
      var lh = (nodeHealth(da)==='bad' || nodeHealth(db)==='bad') ? 'bad' : 'ok';
      parts.push('<line class="link-line '+lh+'" x1="'+(a.x+a.w)+'" y1="'+(a.y+a.h/2)+'" x2="'+b.x+'" y2="'+(b.y+b.h/2)+'"/>');
    }
    nodes.forEach(function(d){
      var dev = devs[d.name] || {};
      var st = nodeHealth(dev);
      parts.push('<rect class="node-box '+st+'" x="'+d.x+'" y="'+d.y+'" rx="12" ry="12" width="'+d.w+'" height="'+d.h+'"/>');
      parts.push('<text class="node-title" x="'+(d.x+14)+'" y="'+(d.y+30)+'">'+esc(d.name)+'</text>');
      parts.push('<text class="node-role" x="'+(d.x+14)+'" y="'+(d.y+50)+'">'+esc(dev.role||'FRR')+'</text>');
      var info = [];
      var p = dev.parsed;
      if(p && p.ospf_peers && p.ospf_peers.length) info.push('OSPF: ' + p.ospf_peers.map(function(x){ return x.id+' '+x.state; }).join(' / '));
      if(p && p.bgp_peers && p.bgp_peers.length) info.push('eBGP: ' + p.bgp_peers.map(function(x){ return x.peer+'→'+(x.state.match(/^\d+$/)?'Established':x.state); }).join(' / '));
      if(!info.length) info.push(p && p.routes && p.routes.length ? '路由 '+p.routes.length+' 条' : '（无邻居数据）');
      var t = info[0] || ''; if(t.length>34) t=t.slice(0,33)+'…';
      parts.push('<text class="node-sub" x="'+(d.x+14)+'" y="'+(d.y+70)+'">'+esc(t)+'</text>');
      var fb = faultBadge(dev);
      if(fb) parts.push('<text class="node-fault" x="'+(d.x+14)+'" y="'+(d.y+106)+'">'+esc(fb)+'</text>');
    });
    parts.push('</svg>');
    svgBox.innerHTML = parts.join('');
  }

  function esc(s){ return String(s == null ? '' : s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }

  function renderTopoCards(devs){
    var order = ['frr1','frr2','frr3'];
    var html = order.map(function(n){
      var dev = devs[n];
      if(!dev) return '';
      var st = nodeHealth(dev);
      var stTxt = st === 'ok' ? '正常' : (st === 'bad' ? '异常' : (st === 'warn' ? '故障演练中' : '未知'));
      var stCls = st;
      var fb = faultBadge(dev);
      var p = dev.parsed || {};
      var ospf = (p.ospf_peers || []).map(function(x){ return '<tr><td>'+esc(x.id)+'</td><td>'+esc(x.state)+'</td><td>'+esc(x.address)+'</td></tr>'; }).join('');
      var bgp = (p.bgp_peers || []).map(function(x){ return '<tr><td>'+esc(x.peer)+'</td><td>'+esc(x.as)+'</td><td>'+(/^\d+$/.test(x.state)?'<span class="t-green">Established('+esc(x.state)+')</span>':'<span class="t-red">'+esc(x.state)+'</span>')+'</td></tr>'; }).join('');
      var routes = (p.routes || []).slice(0,6).map(function(r){ return esc(r); }).join('\n');
      return '<div class="dev-card">'
        + '<h3><span class="st ' + stCls + '"></span>' + esc(n) + ' <span class="t-dim">(' + esc(dev.role || '') + ' · ' + stTxt + ')</span></h3>'
        + '<div class="meta">' + esc(dev.host || '') + ':' + (dev.port || '') + ' · ' + (dev.note || '') + '</div>'
        + (fb ? '<div style="margin:6px 0;padding:6px 10px;background:rgba(250,173,20,.12);border:1px solid rgba(250,173,20,.4);border-radius:8px;color:#FAAD14;font-size:12px;font-weight:600;">' + esc(fb) + '</div>' : '')
        + (ospf ? '<div class="sect">OSPF 邻居</div><table><tr><th>Router ID</th><th>State</th><th>Address</th></tr>' + ospf + '</table>' : '')
        + (bgp ? '<div class="sect">eBGP 邻居</div><table><tr><th>Peer</th><th>AS</th><th>State/PfxRcd</th></tr>' + bgp + '</table>' : '')
        + (routes ? '<div class="sect">路由表（前 6 条）</div><pre>' + esc(routes) + '</pre>' : '')
        + '</div>';
    }).join('');
    topoCards.innerHTML = html;
  }

  var topoTimer = null;

  function showTopoState(bannerHtml, svgHint){
    // 统一降级：清空拓扑 + 顶部横幅 + 中央提示
    topoBanner.style.display = 'block';
    topoBanner.innerHTML = bannerHtml;
    svgBox.innerHTML = '<div class="topo-hint">' + svgHint + '</div>';
    topoCards.innerHTML = '';
  }
  function bindStartDockerBtn(){
    var sdb = document.getElementById('startDockerBtn');
    if(sdb) sdb.addEventListener('click', function(){
      sdb.textContent = '启动中…'; sdb.disabled = true;
      apiFetch('/api/docker/start', {method:'POST'}).then(function(r){ return r.json(); }).then(function(r){
        if(r.ok){ setStatus(r.message); setTimeout(function(){ loadTopo(true); }, 3000); }
        else { alert(r.message || '启动失败'); }
        sdb.textContent = '启动 Docker'; sdb.disabled = false;
      }).catch(function(e){ alert('启动失败：' + e.message); sdb.textContent='启动 Docker'; sdb.disabled=false; });
    });
  }

  function loadTopo(manual){
    if(manual) topoRefresh.disabled = true;
    apiFetch('/api/topology/real')
      .then(function(r){ if(!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
      .then(function(d){
        topoRefresh.disabled = false;
        var hasDevices = d.devices && Object.keys(d.devices).length > 0;
        if(!d.ok || !hasDevices){
          // 状态 B：Docker 未启用 / 无 FRR 容器 → 拓扑消失 + 启动按钮
          var reason = (d.message || (d.docker_available === false ? 'Docker 服务未启用' : '未检测到 FRR 容器')).replace(/[<>&]/g,'');
          showTopoState(
            '未检测到 Docker 服务 <button id="startDockerBtn" style="margin-left:10px;padding:4px 12px;background:linear-gradient(135deg,#7CB342,#558B2F);color:#fff;border:none;border-radius:8px;cursor:pointer;">启动 Docker</button>',
            '未检测到 Docker · ' + reason
          );
          bindStartDockerBtn();
          return;
        }
        // 状态 A：Docker 正常 → 渲染真实拓扑
        topoBanner.style.display = 'none';
        renderTopoSvg(d.devices);
        renderTopoCards(d.devices);
        loadTimeline();
        setStatus('真实拓扑已刷新 · ' + new Date().toLocaleTimeString());
      })
      .catch(function(e){
        topoRefresh.disabled = false;
        // 状态 C：后端不可达（非 Docker 问题）→ 明确提示，不误报 Docker
        showTopoState(
          '后端服务未连接（请双击 start_backend.bat 启动后端）',
          '后端未连接，无法读取拓扑'
        );
      });
    // 轮询始终运行（无论成功失败），Docker 中途断开/恢复都会被捕获
    if(!topoTimer){ topoTimer = setInterval(function(){ if(autoRefresh.checked) loadTopo(false); }, 5000); }
  }
  // ---- 事件时间线（方向1）：读审计流，垂直时间轴展示 ----
  function tlClass(ev){
    var e = (ev.event || '') + ' ' + (ev.action || '');
    if(e.indexOf('frr') >= 0 || e.indexOf('inject') >= 0 || e.indexOf('recover') >= 0) return 'b-frr';
    if(e.indexOf('alert') >= 0 || e.indexOf('webhook') >= 0) return 'b-alert';
    if(e.indexOf('scenario') >= 0) return 'b-scn';
    if(e.indexOf('tool') >= 0) return 'b-tool';
    if(e.indexOf('chat') >= 0) return 'b-chat';
    return 'b-other';
  }
  function tlLabel(cls){ return cls.replace('b-','').toUpperCase(); }
  function loadTimeline(){
    apiFetch('/api/events/timeline?limit=30').then(function(r){ return r.json(); }).then(function(d){
      var list = document.getElementById('tlList');
      var meta = document.getElementById('tlMeta');
      if(!d.events || !d.events.length){ list.innerHTML = '<div class="topo-hint">暂无事件</div>'; return; }
      meta.textContent = '最近 ' + d.events.length + ' 条 · 实时审计流';
      list.innerHTML = d.events.map(function(ev){
        var t = (ev.ts || '').replace('T',' ').substring(5,19);
        var cls = tlClass(ev);
        var actor = ev.actor ? '<span class="tl-actor">[' + esc(ev.actor) + ']</span> ' : '';
        return '<div class="tl-item"><span class="tl-time">' + esc(t) + '</span>'
          + '<span class="tl-badge ' + cls + '">' + tlLabel(cls) + '</span>'
          + '<span class="tl-detail">' + actor + esc((ev.action||'') + (ev.detail ? ' · ' + ev.detail : '')) + '</span></div>';
      }).join('');
    }).catch(function(){ /* 静默：拓扑页主流程不受影响 */ });
  }
  topoRefresh.addEventListener('click', function(){ loadTopo(true); });

  // ---- 一键恢复全部 FRR 故障（演练后兜底，admin） ----
  var topoRecover = document.getElementById('topoRecover');
  topoRecover.addEventListener('click', function(){
    if(document.getElementById('startDockerBtn')){
      alert('Docker 未启用，请先点击「启动 Docker」再恢复故障。');
      return;
    }
    topoRecover.disabled = true;
    topoRecover.textContent = '恢复中…';
    apiFetch('/api/frr/recover-all', {method:'POST'}).then(function(r){ return r.json(); }).then(function(d){
      topoRecover.disabled = false;
      topoRecover.textContent = '一键恢复';
      if(d.ok){
        setStatus('已恢复 ' + d.recovered.length + ' 个故障组合' + (d.errors && d.errors.length ? '（' + d.errors.length + ' 个失败：' + d.errors.join('; ') + '）' : ''));
        loadTopo(true);
      }else{ alert('恢复失败：' + (d.message || '未知错误')); }
    }).catch(function(e){
      topoRecover.disabled = false;
      topoRecover.textContent = '一键恢复';
      alert('恢复失败：后端未连接或已退出，请双击 start_backend.bat 重启后端后重试。');
    });
  });

  // ---- 布局切换（分栏/仅对话/仅拓扑） ----
  document.querySelectorAll('.navtab').forEach(function(tab){
    tab.addEventListener('click', function(){
      document.querySelectorAll('.navtab').forEach(function(t){ t.classList.remove('active'); });
      tab.classList.add('active');
      var layout = tab.getAttribute('data-layout');
      document.body.className = document.body.className.replace(/layout-\w+/g,'').trim();
      document.body.classList.add('layout-' + layout);
      if(layout === 'topo' || layout === 'split'){ loadTopo(true); }
    });
  });

  // ---- 会话侧栏：多会话列表 / 新建 / 切换 ----
  var sbList = document.getElementById('sbList');
  var newChatBtn = document.getElementById('newChatBtn');

  function renderSessions(list){
    currentSessionsCache = list || [];
    sbList.innerHTML = list.map(function(s){
      var active = (s.session_id === sessionId) ? ' active' : '';
      var d = new Date(s.updated * 1000);
      var ts = (d.getMonth()+1) + '/' + d.getDate() + ' ' + ('0'+d.getHours()).slice(-2) + ':' + ('0'+d.getMinutes()).slice(-2);
      var title = esc(s.title || s.session_id.slice(-8));
      return '<div class="sb-item' + active + '" data-sid="' + esc(s.session_id) + '" title="' + esc(title) + '">'
        + '<div style="flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">' + esc(title) + '</div>'
        + '<div class="sb-del" data-del="' + esc(s.session_id) + '" title="删除">×</div>'
        + '<div style="font-size:10px;opacity:.6;width:100%;">' + s.messages + ' 条 · ' + ts + '</div></div>';
    }).join('');
    sbList.querySelectorAll('.sb-item').forEach(function(el){
      el.addEventListener('click', function(e){
        if(e.target.classList.contains('sb-del')) return;
        switchSession(el.getAttribute('data-sid'));
      });
    });
    sbList.querySelectorAll('.sb-del').forEach(function(btn){
      btn.addEventListener('click', function(e){
        e.stopPropagation();
        var sid = btn.getAttribute('data-del');
        if(btn.dataset.confirming){
          // 第二次点：确认删除
          apiFetch('/api/session/' + encodeURIComponent(sid), {method:'DELETE'}).then(function(){
            refreshSessions();
            if(sid === sessionId){
              abortStream();  // 删除当前会话时中止进行中的流
              clearChatDom();
              appendMsg('bot', '已删除当前会话，点左上角「+ 新建」开始新对话。');
            }
          }).catch(function(e){ alert('删除失败：' + e.message); });
          return;
        }
        // 第一次点：变成确认状态
        btn.dataset.confirming = '1';
        btn.textContent = '✓';
        btn.style.background = '#E57373';
        var cancel = document.createElement('div');
        cancel.className = 'sb-del';
        cancel.textContent = '✗';
        cancel.style.background = '#9FB4BD';
        cancel.addEventListener('click', function(ev){
          ev.stopPropagation();
          renderSessions(currentSessionsCache || []);
        });
        btn.parentNode.insertBefore(cancel, btn.nextSibling);
        // 5 秒后自动还原
        setTimeout(function(){ renderSessions(currentSessionsCache || []); }, 5000);
      });
    });
  }
  var currentSessionsCache = [];

  function refreshSessions(){
    apiFetch('/api/sessions').then(function(r){ return r.json(); }).then(function(d){
      if(d && d.ok) renderSessions(d.sessions || []);
    }).catch(function(){});
  }

  function switchSession(sid){
    if(!sid || sid === sessionId) return;
    abortStream();  // 中止当前流的旧响应，避免写入新会话 DOM
    sessionId = sid;
    localStorage.setItem('netops_sid', sid);
    clearChatDom();
    apiFetch('/api/session/' + encodeURIComponent(sid)).then(function(r){ return r.json(); }).then(function(d){
      if(d && d.ok && d.messages && d.messages.length){
        d.messages.forEach(function(m){
          history.push({role:m.role, content:m.content});
          appendMsg(m.role, m.content || '(空回复)');
        });
      } else {
        appendMsg('bot', '已切换到新会话。');
      }
      refreshSessions();
    }).catch(function(){ appendMsg('bot', '切换会话失败。'); });
  }

  function clearChatDom(){
    chat.innerHTML = '';
    history.length = 0;
  }

  newChatBtn.addEventListener('click', function(){
    var sid = 's-' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 8);
    switchSession(sid);
  });

  refreshSessions();
  setInterval(refreshSessions, 15000);

  // 初始加载拓扑（分栏模式下立即可见）
  loadTopo(true);

  input.focus();
})();
