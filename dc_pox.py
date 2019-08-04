from pox.core import core
import pox.openflow.libopenflow_01 as of
import pox.lib.packet as pkt
import pox.lib.addresses as adrs
import pox.openflow.nicira as nx
from pox.lib.revent import *
from pox.openflow.discovery import Discovery
from pox.lib.util import dpidToStr
from pox.lib.recoco import Timer
from time import time
import math



log = core.getLogger()

analy = False

num_pods = -1
num_switches = 0
cur_num_links = 0

link_timeout = 0
arp_cache_timeout = 2


started = False
last_link_event = 0

#store dpids
all_switches = set()
edge_switches = set()
agg_switches = set()
core_switches = set()

total_ports = {}

#pod:[{pos:dpid}]
ags = []
egs = []

switch_pos = {} #{dpid:[pod,pos]}
assigned_pmac = {}  #{dpid:[]}
ports = {}

g = {}  #{dpid:{src_port:[dst_dpid, dst_port]}}

agg_up_ports = {}
agg_down_ports = {}
host_ports = {}

edge_pmac = {}

events = {}

#ip->pmac
arp_table = {}
pmac_actual = {}
actual_pmac = {}

vmid = 0




def _handle_ConnectionUp (event):

    global num_switches
    num_switches += 1

    g[event.dpid] = {}
    switch_pos[event.dpid] = [-1, -1]

    l = [port.port_no for port in event.ofp.ports]
    if of.OFPP_LOCAL in l:  
        l.remove(of.OFPP_LOCAL)

    total_ports[event.dpid] = len(l)
    ports[event.dpid] = l 
    all_switches.add(event.dpid)
    msg = nx.nx_flow_mod_table_id()
    event.connection.send(msg) 

def _handle_LinkEvent (event):
    
    global cur_num_links
    link = event.link

    if(event.added):  
        g[link.dpid1][link.port1] = [link.dpid2, link.port2]
        cur_num_links += 1
        if link_timeout:
           global last_link_event
           last_link_event = int(time())
           Timer(link_timeout, _check)

def _check():
    if ( not started and ( int(time()) - last_link_event ) >= link_timeout ):
        _start()

def _start():
    global started

    if started:
        return
    started = True
    log.info( ' Total num_switches:{0}, num_links:{1}'.format(num_switches, cur_num_links) )
    global core_switches
    global edge_pmac
    log.info( '\nGraph : {0}'.format(g))

    for dpid,links in g.iteritems():
        if ((total_ports[dpid])-len(links)) > 0:  
            edge_switches.add(dpid)
            assigned_pmac[dpid] = {}
            edge_pmac[dpid]=[]
            host_ports[dpid] = list( set(ports[dpid]) - set(g[dpid].keys()) )
            for port in host_ports[dpid]:
                assigned_pmac[dpid][port] = vmid
 
    for dpid in edge_switches:  
        links = g[dpid]
        for src_port,link in links.iteritems():
            if link[0] not in agg_switches: 
                agg_switches.add(link[0])
                agg_down_ports[link[0]] = []
            agg_down_ports[link[0]].append(link[1])
    core_switches = all_switches.difference(agg_switches.union(edge_switches))
   
    for dpid in agg_switches:
        agg_up_ports[dpid] = list( set(g[dpid].keys()) - set(agg_down_ports[dpid]) )

    log.info( '\nEdge switches : {0}'.format(edge_switches) )
    log.info( '\nAggregate switches : {0}'.format(agg_switches) )
    log.info( '\nCore switches : {0}'.format(core_switches) )


    en_dis_agg_core_links() 

    pod = 0
    for agg in agg_switches:
        if switch_pos[agg][0] == -1 :  
            bfs(agg, pod)
            pod += 1
    global num_pods
    num_pods = pod

    en_dis_agg_core_links() 

    log.info( 'Nume of pods : {0} \nSwitch positions : {1} '.format( num_pods, switch_pos ) )

    insert_routes()

    for es in edge_switches:
        msg = nx.nx_flow_mod()
        msg.priority = 9000
        msg.match.eth_type = pkt.ethernet.ARP_TYPE
        msg.actions.append(of.ofp_action_output(port = of.OFPP_CONTROLLER))
        for port in host_ports[es]:
            msg.match.NXM_OF_IN_PORT = port
            core.openflow.connections[es].send(msg)
        msg = nx.nx_flow_mod(table_id = 0)
        msg.priority = 10
        msg.actions.append(nx.nx_action_resubmit.resubmit_table(table=1))
        core.openflow.connections[es].send(msg)
        msg = nx.nx_flow_mod(table_id = 1)
        msg.priority = 10
        msg.actions.append(nx.nx_action_resubmit.resubmit_table(table=2))
        core.openflow.connections[es].send(msg)

    core.openflow.addListenerByName("PacketIn", _handle_PacketIn)
    print 'Ready for some fun'

def en_dis_agg_core_links():  
      
    for core_switch in core_switches:
        links = g[core_switch]
       
        for src_port,link in links.iteritems():
            agg_link = g[link[0]][link[1]]
            agg_link[0] = -agg_link[0]
     

def bfs(dpid, pod):
    egs.append({})
    ags.append({})
    q = [dpid]
    pos = 0
    while len(q) != 0 :
        dpid = q.pop(0)
        if switch_pos[dpid][0] == -1 :
            if dpid in edge_switches:
                egs[pod][pos] = dpid
            elif dpid in agg_switches:
                ags[pod][pos] = dpid
            switch_pos[dpid][0] = pod
            switch_pos[dpid][1] = pos
            pos += 1
            links = g[dpid]
            for src_port,link in links.iteritems():
                if ( (link[0] > 0) and (switch_pos[link[0]][0] == -1) ): 
                    q.append(link[0])

def insert_routes():
    for core_switch in core_switches:
        links=g[core_switch]
	switches=[[] for i in range(num_pods)]
        
        con = core.openflow.connections[core_switch]
	for src_port,link in links.iteritems():
	    pod=switch_pos[link[0]][0]
	    switches[pod].append(src_port)
	for pod_num in range(num_pods):
	    num_routes = len(switches[pod_num])    
	    if num_routes > 1:
                msg_cs = nx.nx_flow_mod(table_id = 0)
                msg_cs.priority = 2000
                num_bits  = int(math.floor(math.log(num_routes, 2)))
                x = 2 ** num_bits   
                mask = 'ff:ff:00:' + eth_addr_format(x - 1, 2) + ':00:00'
                mask_for_bcast = '00:00:00:' + eth_addr_format(x - 1, 2) + ':00:00'
                prefix = eth_addr_format(pod_num, 4) + ':00:'
                suffix = ':00:00'
                for i in range(num_routes):
                    port = i % x
                    port_mask = prefix + eth_addr_format(port, 2) + suffix
                    msg_cs.match.eth_dst_with_mask = ( port_mask, mask)
                    dst_port = switches[pod_num][i]
                    msg_cs.actions = [of.ofp_action_output(port = dst_port)]
                    key = ('00:00:00:' + eth_addr_format(port, 2) + ':00:00', mask_for_bcast)
                    con.send(msg_cs)
            else:
                msg_cs = nx.nx_flow_mod(table_id = 0)
                msg_cs.priority = 2000
                msg_cs.match.eth_dst_with_mask = ( eth_addr_format(pod_num, 4) + ":00:00:00:00", "ff:ff:00:00:00:00")
                msg_cs.actions.append(of.ofp_action_output(port = switches[pod_num][0]))
                con.send(msg_cs)
       

    for agg_switch in agg_switches:
        con = core.openflow.connections[agg_switch]
        up_ports = agg_up_ports[agg_switch]
        num_routes = len(up_ports)
        if num_routes > 1: 
            msg_as = nx.nx_flow_mod(table_id = 0)
            msg_as.priority = 2000
            num_bits  = int(math.floor(math.log(num_routes, 2)))
            x = 2 ** num_bits  
            mask = '00:00:00:' + eth_addr_format(x - 1, 2) + ':00:00'
            prefix = '00:00:00:'
            suffix = ':00:00'
            for i in range(num_routes):
                port = i % x
                msg_as.match.eth_dst_with_mask = ( prefix + eth_addr_format(port, 2) + suffix, mask)
                msg_as.actions = [ of.ofp_action_output(port = up_ports[i]) ]
                con.send(msg_as)
        else:
            msg_as = nx.nx_flow_mod(table_id = 0)
            msg_as.priority = 2000
            msg_as.actions.append(of.ofp_action_output(port = up_ports[0]))
            con.send(msg_as)
      
        down_ports = agg_down_ports[agg_switch]
        pod_num = switch_pos[agg_switch][0]
        prefix = eth_addr_format(pod_num , 4) + ':'
        suffix = ':00:00:00'
        mask = 'ff:ff:ff:00:00:00'
        msg_as = nx.nx_flow_mod(table_id = 0)
        msg_as.priority = 3000

        for src_port in down_ports:
            pos = switch_pos[g[agg_switch][src_port][0]][1]
            msg_as.match.eth_dst_with_mask = ( prefix + eth_addr_format(pos, 2) + suffix, mask)
            msg_as.actions = [ of.ofp_action_output(port = src_port) ]
            con.send(msg_as)
    
    for edge_switch in edge_switches:
        con = core.openflow.connections[edge_switch]
        up_ports = g[edge_switch].keys()
        num_routes = len(up_ports)
        if num_routes > 1:  
            msg_es = nx.nx_flow_mod(table_id = 2)
            msg_es.priority = 8500
            num_bits  = int(math.floor(math.log(num_routes, 2)))
            x = 2 ** num_bits  
            mask = '00:00:00:' + eth_addr_format(x - 1, 2) + ':00:00'
            prefix = '00:00:00:'
            suffix = ':00:00'
            for i in range(num_routes):
                port = i % x
                msg_es.match.eth_dst_with_mask = ( prefix + eth_addr_format(port, 2) + suffix, mask)
                msg_es.actions = [ of.ofp_action_output(port = up_ports[i]) ]
                con.send(msg_es)
        else:
            msg_es = nx.nx_flow_mod(table_id = 2)
            msg_es.priority = 8500
            msg_es.actions.append(of.ofp_action_output(port = up_ports[0]))
            con.send(msg_es)

def _handle_PacketIn(event):

    if event.port == of.OFPP_LOCAL:
        log.info('From OPENFLOW port')
        return
    if event.parsed.type != pkt.ethernet.ARP_TYPE and event.parsed.type != 34525:
       if analy == True:
          eth_pkt = event.parsed
          po = int(eth_pkt.dst.toStr()[9:11])
          packets_rec[event.dpid][po][eth_pkt.dst.toStr()] += 1 
          packets_port[event.dpid][po] += 1
          
    if event.parsed.type == pkt.ethernet.ARP_TYPE:
        log.info("PacketIn : dpid:{0},port:{1},src:{2},dst:{3}".format(event.dpid, event.port, event.parsed.src.toStr(), event.parsed.dst.toStr()))
        
        _process_arp_packet_in(event)
   

def _process_arp_packet_in(event):

    eth_pkt = event.parsed
    arp_pkt = event.parsed.payload
    log.info('ARP packet : type: {0}, dst ip:{1}, src ip:{2}, src mac:{3}, dst mac:{4}'.format(arp_pkt.opcode, arp_pkt.protodst.toStr(), arp_pkt.protosrc.toStr(), arp_pkt.hwsrc.toStr(), arp_pkt.hwdst.toStr()))
    org_mac = eth_pkt.src.toStr()
    ip = arp_pkt.protosrc.toStr()
    if ip in arp_table:
       _handle_arp(event)
    elif org_mac in actual_pmac:
        arp_table[ip] = actual_pmac[org_mac]
        _handle_arp(event)
    else:
        pmac = _handle_new_host(org_mac, ip, event.dpid, event.port)
        handler_id = event.connection.addListenerByName("BarrierIn", _handle_BarrierIn_ARP)
        barrier = of.ofp_barrier_request()
        events[barrier.xid] = (handler_id, event, pmac, ip)
        event.connection.send(barrier)
 
def _handle_BarrierIn_ARP(e):
    if e.xid not in events:
        return
    handler, event, pmac, ip = events.pop(e.xid)
    log.debug( 'Barrier received for pmac:{0}'.format(pmac) )
    e.connection.removeListener(handler)

    arp_table[ip] = pmac
    org_mac = event.parsed.src.toStr()
    actual_pmac[org_mac] = pmac
    pmac_actual[pmac] = org_mac
    _handle_arp(event)


def _handle_arp(event):
    
    eth_pkt = event.parsed
    arp_pkt = event.parsed.payload
    org_mac = eth_pkt.src.toStr()
    if org_mac in actual_pmac:
        pmac_src = adrs.EthAddr(actual_pmac[org_mac])
    if arp_pkt.opcode == arp_pkt.REQUEST:
        dst_ip = arp_pkt.protodst.toStr()
        log.debug( 'ARP request : ip:{0}'.format(dst_ip) )
        if dst_ip in arp_table:
            arp_reply = pkt.arp()
            arp_reply.hwsrc = adrs.EthAddr(arp_table[dst_ip])
            arp_reply.hwdst = eth_pkt.src
            arp_reply.opcode = pkt.arp.REPLY
            arp_reply.protosrc = arp_pkt.protodst
            arp_reply.protodst = arp_pkt.protosrc
            ether = pkt.ethernet()
            ether.type = pkt.ethernet.ARP_TYPE
            ether.dst = eth_pkt.src
            ether.src = arp_reply.hwsrc
            ether.payload = arp_reply
            msg = of.ofp_packet_out()
            msg.actions.append(of.ofp_action_output(port = event.port))
            msg.data = ether.pack()
            event.connection.send(msg)
        else:
            log.info( 'Broadcasting since we dont have ARP mapping for ip : {0}'.format(dst_ip) )
            arp_pkt.hwsrc = pmac_src
            eth_pkt.src = pmac_src
            edge_bcast(eth_pkt.pack(), event.dpid, event.port)
    elif arp_pkt.opcode == arp_pkt.REPLY:
        arp_pkt.hwsrc = pmac_src
        eth_pkt.src = pmac_src
        arp_pkt.hwdst = adrs.EthAddr(pmac_actual[arp_pkt.hwdst.toStr()])
        dpid, port = pmac_pos(eth_pkt.dst.toStr())
        eth_pkt.dst = arp_pkt.hwdst
        msg = of.ofp_packet_out()
        msg.actions.append(of.ofp_action_output(port = port))
        msg.data = eth_pkt.pack()
        core.openflow.connections[dpid].send(msg)


def edge_bcast(data, src_dpid, src_port):
    msg = of.ofp_packet_out()
    msg.data = data
    for es in edge_switches:
        msg.actions = [ of.ofp_action_output(port = hp) for hp in host_ports[es] ] 
        if es == src_dpid:
            msg.actions.pop( host_ports[es].index(src_port) )
        core.openflow.connections[es].send(msg)

def _handle_new_host(org_mac, ip, dpid, port,vm_migrated=None):
    con = core.openflow.connections[dpid]
    pmac = _assign_pmac(dpid, port, org_mac)
    if vm_migrated == 1:
       edge_pmac[dpid].remove(actual_pmac[org_mac])
       edge_pmac[dpid].append(pmac)
    else:
       edge_pmac[dpid].append(pmac)
    msg = nx.nx_flow_mod(table_id = 0)
    msg.priority = 5000
    msg.match.NXM_OF_IN_PORT = port
    msg.match.eth_src = org_mac
    msg.actions.append(of.ofp_action_dl_addr.set_src(adrs.EthAddr(pmac)))
    msg.actions.append(nx.nx_action_resubmit.resubmit_table(table=1))
    con.send(msg)
    msg = nx.nx_flow_mod(table_id = 1)
    msg.priority = 5000
    msg.match.eth_dst = pmac
    msg.actions.append(of.ofp_action_output(port = of.OFPP_CONTROLLER))
    msg.actions.append(of.ofp_action_dl_addr.set_dst(adrs.EthAddr(org_mac)))
    msg.actions.append(of.ofp_action_output(port = port))
    con.send(msg)
    return pmac


def _assign_pmac(edge_dpid, port, org_mac):
   
    prefix = (long(switch_pos[edge_dpid][0])<<32) + (switch_pos[edge_dpid][1]<<24) + (port << 16)
    vmid = assigned_pmac[edge_dpid][port]
    assigned_pmac[edge_dpid][port] += 1
    assert assigned_pmac[edge_dpid][port] < 256
    pmac_long = prefix + vmid
    pmac = eth_addr_format(pmac_long)
    log.info("PMAC for "+str(org_mac)+" is "+str(pmac))
    return pmac

def pmac_pos(pmac):
 
    tmp = pmac.replace(':','')
    pod = int(tmp[:4], 16)
    pos = int(tmp[4:6], 16)
    port = int(tmp[6:8], 16)
    return egs[pod][pos], port

      
def eth_addr_format(n, l = 12):
    s = hex(n)[2:]
    if s[-1] == 'L':
        s = s[:-1]
    s = ('0' * (l - len(s) )) + s
    res = ''
    for i in range(0, l-2, 2):
        res = res + s[i:i+2] + ':'
    res = res + s[-2:]
    return res        

""" Packets transmitted and recieved by all the switches """

rx_packets = 0
tx_packets = 0
rx_dropped = 0
tx_dropped = 0
rx_errors = 0
tx_errors = 0
num_sw = 0 #total num of switches
num_done = 0 #num of switches for whom stats have been collected
wait_timeout = 0
handler = {} #{dpid:portstats listner handler}

def port_status():
    global handler
    global num_sw
    num_sw = num_switches
    log.info("Sending port stats req to all {0} switches".format(num_sw))
    for con in core.openflow.connections:
        handler[con.dpid] = con.addListenerByName("FlowStatsReceived", start_listener)
        con.send(of.ofp_stats_request(body=of.ofp_flow_stats_request()))
    Timer(wait_timeout, print_stats)

def start_listener(event):
    event.connection.removeListener(handler[event.dpid])
    global num_done
    global rx_packets
    global tx_packets
    global rx_dropped
    global tx_dropped
    global rx_errors
    global tx_errors
    num_done += 1
    log.info('Received port statistics for switch {0}, stats:{1}'.format(event.dpid,event.stats))
    for port_stats in event.stats:
        if(port_stats.port_no != of.OFPP_LOCAL):
            rx_packets += port_stats.rx_packets
            tx_packets += port_stats.tx_packets
            rx_dropped += port_stats.rx_dropped
            tx_dropped += port_stats.tx_dropped
            rx_errors += port_stats.rx_errors
            tx_errors += port_stats.tx_errors
    if num_done == num_sw:
	num_done =0 
        print_stats()

def print_stats():
    log.info('Aggregated switch stats :\nrx_packets : {0} tx_packets : {1} rx_dropped : {2} tx_dropped : {3} rx_errors : {4} tx_errors : {5}'.format(rx_packets, tx_packets ,rx_dropped ,tx_dropped ,rx_errors ,tx_errors))

def table():
        print packets_port 
        print packets_rec

""" For VM migration """ 
packets_rec = {}  # {dpid:{port:{pamc:pkt_rec}}}
packets_port = {} # {dpid:{port:pkt_rec}
_list = []

def start_analyser():
    global packets_rec
    global packets_port
    global analy 
    analy = True
    packets_rec = {} 
    packets_port = {}
    for x in edge_switches:
        packets_rec[x]={}
        packets_port[x]={}
        for y in host_ports[x]:
            packets_port[x][y] = 0
            packets_rec[x][y] = {} 
            for z in edge_pmac[x]:
                a= int(z[9:11])
                print a
                if y == a:
                   packets_rec[x][y][z] = 0
    print "started analyzing"
    Timer(50,calculate)

def calculate():
   global _list
   for i in packets_port.values():
      for j in i.values():
          _list.append(j)

   cal_mean,cal_SD = mean(_list),SD(_list)
   
   if cal_SD < cal_mean:
      print " no vm to be migrated "
      start_analyser()
   else :
      find_vm()

def find_vm():

   array = sorted([[packets_port[dpid][port],dpid,port] for dpid in packets_port for port in packets_port[dpid]])
   len_arr = len(array)-1
   list_cp = sorted(_list)
   migrating_pmac = []
   
   while 1:
       data = array[len_arr]
       vm = packets_rec[data[1]][data[2]] 
       vm_traffic = [[packets,pmac] for pmac,packets in vm.items()] 
       vm_traffic = sorted(vm_traffic)
       mid = (len(vm_traffic)-1)/2
       count2 = mid 
       for i in range(mid+1): 
          list_cp[i] +=  vm_traffic[count2][0]
          list_cp[len_arr] -= vm_traffic[count2][0]
          _mean,_SD = mean(list_cp),SD(list_cp)
          migrating_pmac.append(vm_traffic[count2][1])          
          count2 -= 1 
          if _SD < _mean:
             break
       len_array -= 1     
   j=0
   start_analyser()
   for i in migrating_pmac: 
     migrate_vm(i,array[j][1],array[j][2])
     j += 1

def migrate_vm(pmac, new_sw, new_port):
    
    ip = 0
    for _ip,p_mac in arp_table:
       if p_mac == pmac:
          ip = _ip 
    old_pmac = pmac
    old_amac = pmac_actual[old_pmac] 
    org_mac = old_amac 
    old_sw, old_port = pmac_pos(old_pmac)
    if (old_sw == new_sw) and (old_port == new_port):
        return 0 
    new_sw_con = core.openflow.connections[new_sw]
    new_pmac = _handle_new_host(org_mac, ip, new_sw, new_port,1)
   
    handler_id = [0,0]
    barrier_ns = of.ofp_barrier_request()
    xid_ns = barrier_ns.xid
    def _handle_BarrierIn_Mig_NS(e):
        if e.xid != xid_ns: 
            return
        log.debug( 'Barrier received for migrated pmac:{0}'.format(new_pmac) )
        e.connection.removeListener(handler_id[0])

        old_sw_con = core.openflow.connections[old_sw]
        msg = nx.nx_flow_mod(table_id = 0)
        msg.priority = 8000
        msg.idle_timeout = arp_cache_timeout
        msg.match.eth_dst = old_pmac
        rewrite_action = of.ofp_action_dl_addr.set_dst(adrs.EthAddr(new_pmac))
        msg.actions.append(rewrite_action)
        
        up_ports = g[old_sw].keys()
        num_routes = len(up_ports)
      
        if num_routes == 1: 
            msg.actions = [ rewrite_action, of.ofp_action_output(port = of.OFPP_IN_PORT) ]
            old_sw_con.send(msg)
        elif num_routes == 2:
            msg.match.NXM_OF_IN_PORT = up_ports[0]
            msg.actions = [ rewrite_action, of.ofp_action_output(port = up_ports[1] ) ]
            old_sw_con.send(msg)
            msg.match.NXM_OF_IN_PORT = up_ports[1]
            msg.actions = [ rewrite_action, of.ofp_action_output(port = up_ports[0] ) ]
            old_sw_con.send(msg)
        else: 
            num_routes -= 1 
            num_bits  = int(math.floor(math.log(num_routes, 2)))
            x = 2 ** num_bits  
            mask = '00:00:00:' + eth_addr_format(x - 1, 2) + ':00:00'
            prefix = '00:00:00:'
            suffix = ':00:00'
            for j in range(num_routes + 1):
                extra_ports = list(up_ports)
                msg.match.NXM_OF_IN_PORT = extra_ports.pop(j) 
                for i in range(num_routes):
                    port = i % x
                    msg.match.eth_src_with_mask = ( prefix + eth_addr_format(port, 2) + suffix, mask)
                    msg.actions = [ rewrite_action, of.ofp_action_output(port = extra_ports[i]) ]
                    old_sw_con.send(msg)

        msg = nx.nx_flow_mod(table_id = 0, command=of.OFPFC_DELETE)
        msg.priority = 5000
        msg.match.NXM_OF_IN_PORT = old_port
        msg.match.eth_src = old_amac
        old_sw_con.send(msg)
        msg = nx.nx_flow_mod(table_id = 1, command=of.OFPFC_DELETE)
        msg.priority = 5000
        msg.match.eth_dst = old_pmac
        old_sw_con.send(msg)
        
        barrier_os = of.ofp_barrier_request()
        xid_os = barrier_os.xid
        def _handle_BarrierIn_Mig_OS(e):
           
            if e.xid != xid_os:
                return
            log.debug( 'Barrier received for diverting flows to pmac:{0}'.format(new_pmac) )
            e.connection.removeListener(handler_id[1])
            arp_table[ip] = new_pmac
            actual_pmac.pop( pmac_actual.pop(old_pmac) )
            actual_pmac[org_mac] = new_pmac
            pmac_actual[new_pmac] = org_mac
            def _remove_old_pmac():
                assigned_pmac[old_sw][old_port] -= 1
            Timer(arp_cache_timeout, _remove_old_pmac)
        handler_id[1] = old_sw_con.addListenerByName("BarrierIn", _handle_BarrierIn_Mig_OS)
        old_sw_con.send(barrier_os)
    handler_id[0] = new_sw_con.addListenerByName("BarrierIn", _handle_BarrierIn_Mig_NS)
    new_sw_con.send(barrier_ns)
    log.info('IP:{0} moved to edge switch:{1} port:{2}'.format(ip, new_sw, new_port))
    return 1
      
def mean(x):
   return round(sum(x)*1.0/len(x),4)

def SD(x):
   me = mean(x)
   sumx = 0
   for i in range(len(x)):
      sumx += (x[i]-me)**2
   to_root = sumx*1.0/len(x)     
   return math.sqrt(toroot)

def launch(link_interval = 0,wait_time=30):
   
    global link_timeout
    link_timeout = int(link_interval)
    global wait_timeout
    wait_timeout = int(wait_time)
    if not link_timeout:
        link_timeout = 5
    log.info( 'Max interval between two link discovery events : {0}'.format(link_timeout))
    core.openflow.addListenerByName("ConnectionUp", _handle_ConnectionUp)
    core.openflow_discovery.addListenerByName("LinkEvent", _handle_LinkEvent)
    core.Interactive.variables['pktcount'] = port_status
    core.Interactive.variables['table'] = table
    core.Interactive.variables['start'] = start_analyser



