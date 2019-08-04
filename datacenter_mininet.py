
from mininet.topo import Topo
from mininet.cli import CLI
from mininet.log import setLogLevel
from mininet.net import Mininet
import time
class datacenter( Topo ):
   

    def __init__(self, num_pods = 2, num_core = 2, num_agg = 2, num_edge = 4, num_hosts = 2, **opts):
       

        
        Topo.__init__( self )
        
        cs = []
        ags = []
        egs = []	
        hosts = []

        count = 1
        num_links = 0

        for i in xrange(1, num_pods + 1):
            ags.append([])
            egs.append([])
            hosts.append([])
            for j in xrange(1, num_agg + 1):
                s = self.addSwitch(('a_' + str(j) + '_' + str(i)), dpid=str(count))
                ags[i-1].append(s)
		count += 1
            for j in xrange(1, num_edge + 1):                
                s = self.addSwitch(('e_' + str(j) + '_' + str(i)), dpid=str(count))
                egs[i-1].append(s)
		count += 1
                hosts[i-1].append([])
                for m in xrange(1, num_hosts+1):
                    h = self.addHost('h' + str(m) + '_' + str(j) + '_' + str(i))
                    hosts[i-1][j-1].append(h)

       
	
        for i in xrange(1, num_core + 1):
            s = self.addSwitch('c' + str(i), dpid=str(count))
            cs.append(s)
	    count += 1


       	
        for i in xrange(num_pods):
            for j in xrange(num_agg):
                for k in xrange(num_core):
                    self.addLink(ags[i][j],cs[k])
                    num_links += 1




        for i in xrange(num_pods):
            for j in xrange(num_agg):
                for k in xrange(num_edge):
                    self.addLink(ags[i][j],egs[i][k])
                    num_links += 1
                    
                    
   
        for i in xrange(num_pods):
            for j in xrange(num_edge):
                for k in xrange(num_hosts):
                    self.addLink(egs[i][j], hosts[i][j][k])


topos = { 'DC': ( lambda num_pods = 2, num_core = 2, num_agg = 2, num_edge = 4, num_hosts = 2 : datacenter(num_pods,num_core,num_agg,num_edge,num_hosts) ) }
