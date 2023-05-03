import time
import json
import traceback
import subprocess
import logging

from ZookeeperAPI import ZookeeperAPI

import grpc
import detection_pb2
import detection_pb2_grpc
from detection_client import DetectionClient

from scapy.all import *
import argparse # for argument parsing
import configparser # for configuration parsing

class DetectionAppln ():
    def __init__(self, logger):
        self.node = None
        self.zk_api = ZookeeperAPI(logger)
        self.detection_client = DetectionClient('192.168.2.209','50051')

    def configure (self, args):
        self.zk_api.configure()
        self.zk_api.start ()
        self.zk_api.dump ()
        self.node = args.node

    def init_znode (self, node):
        path = self.zk_api.detection_root_path + "/" + node
        if not self.zk_api.zk.exists(path):
            value = "0" + ":" + json.dumps([])
            self.zk_api.zk.create(path, value.encode('utf-8'), makepath=True, ephemeral=True)

    def detection_watch (self):
        for node in self.zk_api.nodes:
            # Initialize the znode
            self.init_znode(node)
            # Watch the node for any changes
            @self.zk_api.zk.DataWatch(self.zk_api.detection_root_path + "/" + node)
            def watch_node (data, stat, event):
                try:
                    print ("Watcher called")
                    print ("Watch Node: " + node)
                    print ("Event Watcher: " + str(event))
                    print ("Data Watcher: " + data.decode("utf-8"))
                    print ("Stat Watcher: " + str(stat))
                    # Parse the data to get the source IP
                    flag, ips = self.parse_data(data)
                    # Call the detection service
                    for ip in ips:
                        if self.detect(ip):
                            self.set_quarantine_signal(node, ip)
                except Exception as e:
                    traceback.print_exc()
                    raise e

    def parse_data (self, data):
        flag, history = data.decode("utf-8").split(":")
        ips = json.loads(history)
        return flag, ips

    def detect (self, ip): 
        # Call the detection service
        response = self.detection_client.run(ip)
        return response
    
    def set_quarantine_signal (self, node, ip):
        # Get the data from the znode
        data, stat = self.zk_api.zk.get (self.zk_api.mitigation_root_path + "/" + node)
        # Parse the data to get the source IP
        flag, ips = self.parse_data(data)
        # Add the new IP to the list
        ips.append(ip)
        # Update the znode
        path = self.zk_api.mitigation_root_path + "/" + node
        value = "1" + ":" + json.dumps(ips)
        self.zk_api.zk.set (path, value.encode('utf-8'))
    
    def event_loop (self):
        print ("Event loop started")
            
        def packet_callback(packet):
            if packet.haslayer(IP):
                if self.detect(packet[IP].src):
                    print("Attack from C&C server")
                    self.set_quarantine_signal(self.node, packet[IP].src)
                else:
                    print("Normal traffic from " + packet[IP].src)

        sniff(prn=packet_callback, filter="tcp", iface="ens3")

    def __del__ (self):
        self.zk_api.shutdown()


def parseCmdLineArgs ():
    # instantiate a ArgumentParser object
    parser = argparse.ArgumentParser (description="Publisher Application")
    
    # Now specify all the optional arguments we support
    # At a minimum, you will need a way to specify the IP and port of the lookup
    # service, the role we are playing, what dissemination approach are we
    # using, what is our endpoint (i.e., port where we are going to bind at the
    # ZMQ level)
    
    parser.add_argument ("-n", "--node", default="host1", help="Some host name, host1/host2/host3")
    return parser.parse_args()


if __name__ == "__main__":
    # set underlying default logging capabilities
    logging.basicConfig (level=logging.DEBUG,
                        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    logger = logging.getLogger (__name__)
    args = parseCmdLineArgs ()
    detection_appln = DetectionAppln(logger)
    detection_appln.configure(args)
    #detection_appln.detection_watch()
    detection_appln.event_loop() 


