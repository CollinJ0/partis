#!/usr/bin/env python
import sys
import os
import csv
csv.field_size_limit(sys.maxsize)  # make sure we can write very large csv fields
import argparse
current_script_dir = os.path.dirname(os.path.realpath(__file__)).replace('/bin', '/python')
if not os.path.exists(current_script_dir):
    print 'WARNING current script dir %s doesn\'t exist, so python path may not be correctly set' % current_script_dir
sys.path.insert(1, current_script_dir)

from clusterpath import ClusterPath
from seqfileopener import get_seqfile_info
import utils

parser = argparse.ArgumentParser()
parser.add_argument('infname')
parser.add_argument('--dont-abbreviate', action='store_true', help='Print full seq IDs (otherwise just prints an \'o\')')
parser.add_argument('--n-to-print', type=int, help='How many partitions to print (centered on the best partition)')
parser.add_argument('--datadir', default='data/imgt')
parser.add_argument('--simfname')
parser.add_argument('--is-data', action='store_true')
args = parser.parse_args()

glfo = utils.read_germline_set(args.datadir)

reco_info = None
if args.simfname is not None:
    input_info, reco_info = get_seqfile_info(args.simfname, args.is_data, glfo=glfo)

cp = ClusterPath()
cp.readfile(args.infname)
cp.print_partitions(abbreviate=(not args.dont_abbreviate), n_to_print=args.n_to_print, reco_info=reco_info)
