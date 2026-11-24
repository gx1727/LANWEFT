#!/usr/bin/env python3
"""C↔C peer 传输 Stage 1 的最小逻辑验证（纯内存，无网络）。

模拟 Server / C1 / C2：
  * peer_start/offer/response/accept 握手（没有 C↔C login）
  * 直连数据 + peer PROBE 的 token/源地址绑定
  * 缺失/信用/进度/完成经 Server 中继
  * 中途断线重连（接收方位图保留）
  * R1 预选中转（C1→S upload + S→C2 download）
  * 无 share grant 的授权拒绝、错误 token / 错误源地址丢弃

运行：python3 scripts/verify-peer.py
这不是规范自检；字段级/线格式由 check-spec-consistency.py 覆盖。
"""

import hashlib
import random

SYMBOL=1200; CHUNK=64800; S_FULL=54
C1='C1'; C2='C2'; S='S'
EP1=('10.0.0.1',5001); EP2=('10.0.0.2',5002); EPS=('10.0.0.9',6000)

def cd(a,b): return (a+b-1)//b

class FM:
    def __init__(self,size):
        self.size=size; self.cc=cd(size,CHUNK); self.sc=cd(size,SYMBOL)
        self.S=[S_FULL]*self.cc; self.S[-1]=cd(size-(self.cc-1)*CHUNK,SYMBOL)
        self.full=[(1<<x)-1 for x in self.S]
    def start(self,c,i): return c*CHUNK+i*SYMBOL
    def sym_len(self,c,i): return max(0,min(SYMBOL,self.size-self.start(c,i)))

class RX:
    def __init__(self,fm,sid,token):
        self.fm=fm; self.sid=sid; self.token=token; self.buf=bytearray(fm.size)
        self.masks={}; self.bound=None
    def probe(self,sid,token,src):
        if sid!=self.sid or token!=self.token: return None
        self.bound=src; return True
    def recv(self,sid,cid,csym,payload,crc_ok,src):
        if sid!=self.sid: return 'session'
        if src!=self.bound: return 'source'
        if not crc_ok: return 'crc'
        K=cd(len(payload),SYMBOL)
        if cid>=self.fm.cc or csym+K>self.fm.S[cid]: return 'range'
        tail=(cid==self.fm.cc-1 and csym+K==self.fm.S[cid])
        if not tail and len(payload)%SYMBOL: return 'align'
        off=self.fm.start(cid,csym)
        if off+len(payload)>self.fm.size: return 'eof'
        self.buf[off:off+len(payload)]=payload
        self.masks[cid]=self.masks.get(cid,0)|(((1<<K)-1)<<csym)
        return 'ok'
    def report(self):
        fully=[]; part=[]; miss=0
        for cid in range(self.fm.cc):
            m=self.masks.get(cid,0); f=self.fm.full[cid]
            if m==f: continue
            if m==0: fully.append(cid); miss+=self.fm.S[cid]
            else: part.append((cid,m)); miss+=self.fm.S[cid]-m.bit_count()
        return fully,part,miss
    def received(self): return self.fm.sc-self.report()[2]
    def ok(self,data): return bytes(self.buf)==data

def runs(fm,rep,K):
    fully,part,_=rep; out=[]
    for cid in fully:
        s=0
        while s<fm.S[cid]:
            n=min(K,fm.S[cid]-s); out.append((cid,s,n)); s+=n
    for cid,rmask in part:
        missing=fm.full[cid]^rmask; s=0
        while s<fm.S[cid]:
            if (missing>>s)&1:
                n=0
                while s+n<fm.S[cid] and ((missing>>(s+n))&1) and n<K: n+=1
                out.append((cid,s,n)); s+=n
            else: s+=1
    return out

def send_run(rx,fm,data,sid,cid,s,n,loss,corrupt,src,dst,edges):
    off=fm.start(cid,s); payload=data[off:off+min(n*SYMBOL,fm.size-off)]
    edges.add((src,dst))
    if random.random()<loss: return 'lost'
    return rx.recv(sid,cid,s,payload,random.random()>=corrupt,src)

def send_all(rx,fm,data,sid,K,loss,corrupt,src,dst,edges):
    stat={}
    for cid in range(fm.cc):
        s=0
        while s<fm.S[cid]:
            n=min(K,fm.S[cid]-s)
            r=send_run(rx,fm,data,sid,cid,s,n,loss,corrupt,src,dst,edges)
            stat[r]=stat.get(r,0)+1; s+=n
    return stat

class Server:
    def __init__(self):
        self.events=[]; self.logins=[]; self.shares=set(); self.sessions={}
        self.next=100; self.temp=[]; self.relay_capacity=True
    def login(self,dev):
        self.logins.append(dev); self.events.append(('login',dev,S))
    def peer_start(self,frm,target,file_hash,mode,pref,fm,ports):
        sender=frm if mode=='push' else target
        receiver=target if mode=='push' else frm
        if (sender,receiver,file_hash) not in self.shares:
            self.events.append(('session_abort',S,frm,'ACL_DENY')); return None
        if frm not in self.logins or target not in self.logins:
            self.events.append(('session_abort',S,frm,'SESSION_NOT_FOUND')); return None
        if pref=='relay' and not self.relay_capacity:
            self.events.append(('session_abort',S,frm,'PEER_RELAY_UNAVAILABLE')); return None
        sid=self.next; self.next+=1; token=bytes([sid%256])*16
        sess=dict(id=sid,sender=sender,receiver=receiver,token=token,mode=mode,
                  transport=('relay_r1' if pref=='relay' else 'direct'),
                  file_hash=file_hash,size=fm.size,chunk_size=CHUNK,
                  endpoints={frm:ports[frm]},counterpart=target)
        self.sessions[sid]=sess
        self.events.append(('peer_start',frm,S))
        self.events.append(('peer_offer',S,target))
        return sess
    def peer_response(self,frm,sess,accept,ep):
        if frm!=sess['counterpart']:
            raise AssertionError('response from wrong side')
        sess['endpoints'][frm]=ep
        if not accept:
            self.events.append(('peer_response',frm,S))
            self.events.append(('session_abort',S,frm,'PEER_DECLINED'))
            return None
        self.events.append(('peer_response',frm,S))
        for who in (sess['sender'],sess['receiver']):
            peer=sess['receiver'] if who==sess['sender'] else sess['sender']
            self.events.append(('peer_accept',S,who))
            sess.setdefault('accepts',[]).append((who,'sender' if who==sess['sender'] else 'receiver',
                                                  sess['endpoints'][peer],sess['token']))
        return sess
    def relay_peer(self,sess,kind,frm,payload=None):
        sender,receiver=sess['sender'],sess['receiver']
        if kind in ('missing_chunks','window_update','progress_update','peer_complete','reconcile_request'):
            if frm!=receiver and not (kind=='missing_chunks' and frm==sender):
                raise AssertionError(f'{kind} from wrong side')
            to=sender if frm==receiver else receiver
        elif kind in ('reconcile_response','complete_ack'):
            if frm!=sender: raise AssertionError(f'{kind} from wrong side')
            to=receiver
        elif kind in ('session_pause','session_abort'):
            to=receiver if frm==sender else sender
        else:
            raise AssertionError(kind)
        self.events.append((kind,frm,S))
        self.events.append((kind,S,to))
        return to
    def relay_plan(self,sess,fm,ports):
        up=self.next; self.next+=1; dn=self.next; self.next+=1
        self.temp.append(dict(transfer=sess['id'],file_hash=sess['file_hash'],state='ready'))
        for who in (sess['sender'],sess['receiver']):
            self.events.append(('peer_relay_plan',S,who))
        self.events.append(('upload_accept',S,sess['sender']))
        self.events.append(('download_accept',S,sess['receiver']))
        return up,dn

def is_c2c_control(ev):
    kind,src,dst=ev[0],ev[1],ev[2]
    return src not in (S,) and dst not in (S,) and kind not in ('data','probe','probe_ack')

def direct_case(fm,data,grant,mode='push',K=1,loss=0.01,corrupt=0.005,reconnect=False,seed=1):
    random.seed(seed); srv=Server(); srv.shares.add(grant)
    srv.login(C1); srv.login(C2)
    initiator,target=(C1,C2) if mode=='push' else (C2,C1)
    ports={C1:EP1,C2:EP2}
    sess=srv.peer_start(initiator,target,grant[2],mode,'direct',fm,ports)
    assert sess is not None
    # counterpart responds (target got the offer)
    sess=srv.peer_response(target,sess,True,ports[target])
    sender,receiver=sess['sender'],sess['receiver']
    ep_s,ep_r=ports[sender],ports[receiver]
    rx=RX(fm,sess['id'],sess['token'])
    # wrong token: no bind/ack
    assert rx.probe(sess['id'],b'\x00'*16,ep_s) is None and rx.bound is None
    # data before bind -> source reject
    off=fm.start(0,0); pay=data[off:off+1200]
    assert rx.recv(sess['id'],0,0,pay,True,ep_s)=='source'
    # correct probe binds source
    assert rx.probe(sess['id'],sess['token'],ep_s) is True and rx.bound==ep_s
    # wrong source after bind -> reject
    assert rx.recv(sess['id'],0,0,pay,True,('10.0.0.99',9))=='source'
    edges=set()
    send_all(rx,fm,data,sess['id'],K,loss,corrupt,ep_s,ep_r,edges)
    loops=0; reconnect_done=False
    if reconnect:
        srv.events.append(('session_interrupted',S,receiver))
        srv.login(C1); srv.login(C2)
        new_ep=('10.0.0.11',5011); sess['endpoints'][sender]=new_ep; ep_s=new_ep
        for who in (sender,receiver): srv.events.append(('peer_accept',S,who))
        rx.bound=None
        assert rx.probe(sess['id'],sess['token'],ep_s) is True
        reconnect_done=True
    while rx.report()[2]>0 and loops<200:
        rep=rx.report()
        srv.relay_peer(sess,'missing_chunks',receiver,rep)
        srv.relay_peer(sess,'window_update',receiver,{'received':rx.received(),'max_ok':1200})
        srv.relay_peer(sess,'progress_update',receiver,{'received':rx.received()})
        # optional reconnect halfway (simulate connection drop + re-login + re-accept)
        if False:
            srv.events.append(('session_interrupted',S,receiver))
            srv.login(C1); srv.login(C2)
            new_ep=('10.0.0.11',5011); sess['endpoints'][sender]=new_ep; ep_s=new_ep
            for who in (sender,receiver): srv.events.append(('peer_accept',S,who))
            rx.bound=None
            assert rx.probe(sess['id'],sess['token'],ep_s) is True
            reconnect_done=True
        rs=runs(fm,rep,K)
        for cid,s,n in rs:
            send_run(rx,fm,data,sess['id'],cid,s,n,loss,corrupt,ep_s,ep_r,edges)
        loops+=1
    assert rx.report()[2]==0, 'not complete'
    assert rx.ok(data), 'content mismatch'
    # completion: receiver -> S -> sender ; ack sender -> S -> receiver
    srv.relay_peer(sess,'peer_complete',receiver,{'result':1})
    srv.relay_peer(sess,'complete_ack',sender,{})
    # assertions
    assert not any(is_c2c_control(e) for e in srv.events), 'C2C control leaked'
    assert not any(e[0]=='login' and C1 in (e[1],e[2]) and C2 in (e[1],e[2]) for e in srv.events)
    expected_logins=4 if reconnect else 2
    assert sum(1 for e in srv.events if e[0]=='login')==expected_logins
    assert edges=={(ep_s,ep_r)} or (reconnect and len(edges)==2), 'data path'
    return dict(loops=loops,logins=sum(1 for e in srv.events if e[0]=='login'),
                relay=sum(1 for e in srv.events if e[0]=='missing_chunks' and e[1]==S),
                edges=edges,events=srv.events)

def r1_case(fm,data,grant,seed=7):
    random.seed(seed); srv=Server(); srv.shares.add(grant)
    srv.login(C1); srv.login(C2)
    ports={C1:EP1,C2:EP2}
    sess=srv.peer_start(C1,C2,grant[2],'push','relay',fm,ports)
    sess=srv.peer_response(C2,sess,True,ports[C2])
    up,dn=srv.relay_plan(sess,fm,ports)
    edges=set()
    # upload C1 -> S
    rxS=RX(fm,up,sess['token']); rxS.bound=EP1
    send_all(rxS,fm,data,up,1,0.0,0.0,EP1,EPS,edges)
    assert rxS.ok(data)
    srv.events.append(('upload_complete',S,C1))
    srv.events.append(('complete_ack',C1,S))
    # download S -> C2 ; temp asset authorizes
    assert any(t['file_hash']==grant[2] for t in srv.temp)
    rxC=RX(fm,dn,sess['token']); rxC.bound=EPS
    send_all(rxC,fm,data,dn,1,0.0,0.0,EPS,EP2,edges)
    assert rxC.ok(data)
    srv.events.append(('download_complete',C2,S))
    srv.events.append(('complete_ack',S,C2))
    srv.temp.clear()
    assert edges=={(EP1,EPS),(EPS,EP2)}, edges
    assert not any(is_c2c_control(e) for e in srv.events)
    return dict(edges=edges,ok=True)

class Relay:
    """R2：S 的会话内转发器（校验 C1 的 token/源地址，再发给 C2）。"""
    def __init__(self,sid,token,out,out_src,out_dst,edges):
        self.sid=sid; self.token=token; self.out=out
        self.out_src=out_src; self.out_dst=out_dst; self.edges=edges; self.bound=None
    def probe(self,sid,token,src):
        if sid!=self.sid or token!=self.token: return None
        self.bound=src; return True
    def recv(self,sid,cid,csym,payload,crc_ok,src):
        if sid!=self.sid: return 'session'
        if src!=self.bound: return 'source'
        if not crc_ok: return 'crc'
        self.edges.add((self.out_src,self.out_dst))
        return self.out.recv(sid,cid,csym,payload,True,self.out_src)

def r2_case(fm,data,grant,loss=0.01,seed=5):
    random.seed(seed); srv=Server(); srv.shares.add(grant)
    srv.login(C1); srv.login(C2)
    sess=srv.peer_start(C1,C2,grant[2],'push','direct',fm,{C1:EP1,C2:EP2})
    sess=srv.peer_response(C2,sess,True,EP2)
    # Server 选择 relay_r2：peer_accept 的端点改为 S 中转端点
    sess['transport']='relay_r2'; sess['relay_endpoint']=EPS
    srv.events.append(('peer_accept',S,C1)); srv.events.append(('peer_accept',S,C2))
    rxC=RX(fm,sess['id'],sess['token']); rxC.bound=EPS
    edges=set(); relay=Relay(sess['id'],sess['token'],rxC,EPS,EP2,edges)
    assert relay.probe(sess['id'],b'\x00'*16,EP1) is None
    assert relay.probe(sess['id'],sess['token'],EP1) is True
    send_all(relay,fm,data,sess['id'],1,loss,0.005,EP1,EPS,edges)
    loops=0
    while rxC.report()[2]>0 and loops<200:
        rep=rxC.report()
        srv.relay_peer(sess,'missing_chunks',sess['receiver'],rep)
        srv.relay_peer(sess,'window_update',sess['receiver'],{'received':rxC.received()})
        for cid,s0,n in runs(fm,rep,1):
            send_run(relay,fm,data,sess['id'],cid,s0,n,loss,0.005,EP1,EPS,edges)
        loops+=1
    assert rxC.report()[2]==0 and rxC.ok(data)
    srv.relay_peer(sess,'peer_complete',sess['receiver'],{'result':1})
    srv.relay_peer(sess,'complete_ack',sess['sender'],{})
    assert edges=={(EP1,EPS),(EPS,EP2)}, edges
    assert not any(is_c2c_control(e) for e in srv.events)
    return dict(loops=loops,edges=edges)

def switch_case(fm,data,grant,seed=6):
    random.seed(seed); srv=Server(); srv.shares.add(grant)
    srv.login(C1); srv.login(C2)
    sess=srv.peer_start(C1,C2,grant[2],'push','direct',fm,{C1:EP1,C2:EP2})
    sess=srv.peer_response(C2,sess,True,EP2)
    rxC=RX(fm,sess['id'],sess['token']); rxC.bound=EP1
    edges=set()
    send_all(rxC,fm,data,sess['id'],1,0.01,0.005,EP1,EP2,edges)
    # direct -> relay_r2 中途切换
    srv.events.append(('peer_transport_switch',S,C1))
    srv.events.append(('peer_transport_switch',S,C2))
    sess['transport']='relay_r2'; sess['relay_endpoint']=EPS
    rxC.bound=EPS
    relay=Relay(sess['id'],sess['token'],rxC,EPS,EP2,edges)
    assert relay.probe(sess['id'],sess['token'],EP1) is True
    loops=0
    while rxC.report()[2]>0 and loops<200:
        rep=rxC.report()
        srv.relay_peer(sess,'missing_chunks',sess['receiver'],rep)
        srv.relay_peer(sess,'window_update',sess['receiver'],{'received':rxC.received()})
        for cid,s0,n in runs(fm,rep,1):
            send_run(relay,fm,data,sess['id'],cid,s0,n,0.01,0.005,EP1,EPS,edges)
        loops+=1
    assert rxC.report()[2]==0 and rxC.ok(data)
    srv.relay_peer(sess,'peer_complete',sess['receiver'],{'result':1})
    srv.relay_peer(sess,'complete_ack',sess['sender'],{})
    assert edges=={(EP1,EP2),(EP1,EPS),(EPS,EP2)}, edges
    assert not any(is_c2c_control(e) for e in srv.events)
    return dict(loops=loops,edges=edges)

if __name__=='__main__':
    size=1_000_000; random.seed(0); data=bytes(random.getrandbits(8) for _ in range(size)); fm=FM(size)
    h=hashlib.sha256(data).hexdigest()[:16]
    grant=(C1,C2,h)
    print(f"file={size}B chunk={CHUNK} S={S_FULL} chunks={fm.cc} symbols={fm.sc} lastS={fm.S[-1]}")

    r=direct_case(fm,data,grant,mode='push',K=1,loss=0.01,corrupt=0.005,seed=1)
    print("\n[1] peer 直连 push（K=1, 1% 丢包）")
    print(f"  ok=True logins={r['logins']} missing-relays={r['relay']} loops={r['loops']} data-edges={r['edges']}")
    assert r['logins']==2
    print("  无 C↔C login / 无 C↔C 控制 ✅")

    rp=direct_case(fm,data,grant,mode='pull',K=1,loss=0.01,corrupt=0.005,seed=2)
    print("\n[2] peer 直连 pull（K=1, 1% 丢包）")
    print(f"  ok=True logins={rp['logins']} data-edges={rp['edges']}")

    r54=direct_case(fm,data,grant,mode='push',K=54,loss=0.0,corrupt=0.0,seed=3)
    print("\n[3] peer 直连 push（K=54，无丢包：验证多 symbol 聚合/掩码）")
    print(f"  ok=True loops={r54['loops']} logins={r54['logins']}")

    rr=direct_case(fm,data,grant,mode='push',K=1,loss=0.01,corrupt=0.005,reconnect=True,seed=4)
    print("\n[4] 直连中途断线 + 重连（位图保留）")
    print(f"  ok=True logins={rr['logins']} loops={rr['loops']} data-edges={rr['edges']}")
    assert rr['logins']==4

    r1=r1_case(fm,data,grant)
    print("\n[5] 直连失败 → R1 预选中转")
    print(f"  ok=True data-edges={r1['edges']} temp-asset reclaimed=True")
    assert r1['edges']=={(EP1,EPS),(EPS,EP2)}

    r2=r2_case(fm,data,grant)
    print("\n[6] R2 会话内中转（C1→S→C2）")
    print(f"  ok=True data-edges={r2['edges']} loops={r2['loops']}")
    assert r2['edges']=={(EP1,EPS),(EPS,EP2)}

    sw=switch_case(fm,data,grant)
    print("\n[7] direct → relay_r2 中途切换（位图保留）")
    print(f"  ok=True data-edges={sw['edges']} loops={sw['loops']}")
    assert (EP1,EP2) in sw['edges'] and (EP1,EPS) in sw['edges'] and (EPS,EP2) in sw['edges']

    srv=Server(); srv.relay_capacity=False; srv.shares.add(grant); srv.login(C1); srv.login(C2)
    no=srv.peer_start(C1,C2,h,'push','relay',fm,{C1:EP1,C2:EP2})
    assert no is None and any(e[0]=='session_abort' and e[3]=='PEER_RELAY_UNAVAILABLE' for e in srv.events)
    print("\n[8] 中转容量不足：peer_start 被 PEER_RELAY_UNAVAILABLE 拒绝 ✅")

    # authorization denial
    srv=Server(); srv.login(C1); srv.login(C2)
    no=srv.peer_start(C1,C2,h,'push','direct',fm,{C1:EP1,C2:EP2})
    assert no is None
    assert any(e[0]=='session_abort' and e[3]=='ACL_DENY' for e in srv.events)
    assert not any(e[0]=='peer_offer' for e in srv.events)
    print("\n[9] 无 share grant：peer_start 被 ACL_DENY 拒绝，未发 peer_offer ✅")

    # token/source assertions are inside direct_case; re-state
    print("\n[10] token/源地址：错误 token 不绑定；数据在绑定前/错误源地址均被丢弃 ✅")
