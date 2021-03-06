#!/usr/bin/env python
# has to be its own script, since ete3 requires its own god damn python version, installed in a separated directory
import time
import yaml
import itertools
import glob
import argparse
import copy
import random
import os
import tempfile
import subprocess
import sys
import colored_traceback.always
from collections import OrderedDict
import numpy
import math
try:
    import ete3
except ImportError:
    raise Exception('couldn\'t find the ete3 module. Either:\n          - it isn\'t installed (use instructions at http://etetoolkit.org/download/) or\n          - $PATH needs modifying (typically with the command \'% export PATH=~/anaconda_ete/bin:$PATH\')')

# ----------------------------------------------------------------------------------------
def getgrey(gtype='medium'):
    if gtype == 'medium':
        return '#929292'
    elif gtype == 'light-medium':
        return '#cdcdcd'
    elif gtype == 'light':
        return '#d3d3d3'
    elif gtype == 'white':
        return '#ffffff'
    else:
        assert False

# ----------------------------------------------------------------------------------------
scolors = {
    'novel' : '#ffc300',  # 'Gold'
    'data' : 'LightSteelBlue',
    'pale-green' : '#85ad98',
    'pale-blue' : '#94a3d1',
    'tigger-default' : '#d77c7c', #'#c32222',  # red
    'igdiscover' : '#85ad98', #'#29a614',  # green
    'partis' : '#94a3d1', #'#2455ed',  # blue
    'lbi' : '#94a3d1',
}

listcolors = [getgrey('medium') for _ in range(10)]
listfaces = [
    'red',
    'blue',
    'green',
]
used_colors, used_faces = {}, {}
simu_colors = OrderedDict((
    ('ok', 'DarkSeaGreen'),
    ('missing', '#d77c7c'),
    ('spurious', '#a44949'),
))


# ----------------------------------------------------------------------------------------
def read_input(args):
    with open(args.treefname) as treefile:
        treestr = treefile.read().strip()
    treestr = treestr.replace('[&R] ', '').replace('\'', '')

    return {'treestr' : treestr}

# ----------------------------------------------------------------------------------------
def get_color(smap, info, key=None, val=None):  # specify *either* <key> or <val> (don't need <info> if you're passing <val>)
    if val is None:
        assert key is not None
        if key not in info:
            return getgrey()
        val = info[key]
    rgb_code = smap.to_rgba(val)[:3]
    return plotting.rgb_to_hex(rgb_code)

# ----------------------------------------------------------------------------------------
min_size = 1.5
max_size = 10
opacity = 0.65
fsize = 7

# ----------------------------------------------------------------------------------------
def set_delta_affinities(etree, affyfo):  # set change in affinity from parent for each node, and return a list of all such affinity changes (for normalizing the cmap)
    delta_affyvals = []
    for node in etree.traverse():
        if node.name not in affyfo or node.up is None or node.up.name not in affyfo:
            node.add_feature('affinity_change', None)
            continue
        node.add_feature('affinity_change', affyfo[node.name] - affyfo[node.up.name])
        delta_affyvals.append(affyfo[node.name] - affyfo[node.up.name])

    return delta_affyvals

# ----------------------------------------------------------------------------------------
def get_size(vmin, vmax, val):
    return min_size + (val - vmin) * (max_size - min_size) / (vmax - vmin)

# ----------------------------------------------------------------------------------------
def add_legend(tstyle, varname, all_vals, smap, info, start_column, add_missing=False, add_sign=None, reverse_log=False, n_entries=5, fsize=4, no_opacity=False):
    if len(all_vals) == 0:
        return
    assert add_sign in [None, '-', '+']
    tstyle.legend.add_face(ete3.TextFace('   %s ' % varname, fsize=fsize), column=start_column)
    min_val, max_val = min(all_vals), max(all_vals)
    if min_val == max_val:
        return
    max_diff = (max_val - min_val) / float(n_entries - 1)
    val_list = list(numpy.arange(min_val, max_val + utils.eps, max_diff))  # first value is exactly <min_val>, last value is exactly <max_val> (eps is to keep it from missing the last one)
    # if add_sign is not None and add_sign == '-':  # for negative changes, we have the cmap using abs() and want to legend order to correspond
    #     val_list = reversed(val_list)  # arg, this breaks something deep in the legend maker, not sure what
    key_list = [None for _ in val_list]
    if add_missing:
        val_list += [None]
        key_list += ['missing!']  # doesn't matter what the last one is as long as it isn't in <affyfo>
    for val, key in zip(val_list, key_list):
        tstyle.legend.add_face(ete3.TextFace('', fsize=fsize), column=start_column)
        if smap is None:
            sz = get_size(min_val, max_val, val)
            rface = ete3.RectFace(sz, sz, bgcolor=getgrey(), fgcolor=None)
        else:
            rface = ete3.RectFace(6, 6, bgcolor=get_color(smap, info, key=key, val=val), fgcolor=None)
        if not no_opacity:
            rface.opacity = opacity
        tstyle.legend.add_face(rface, column=start_column + 1)
        tstyle.legend.add_face(ete3.TextFace(('  %s%.4f' % (add_sign if add_sign is not None else '', math.exp(val) if reverse_log else val)) if key is None else '  missing', fsize=fsize), column=start_column + 2)

# ----------------------------------------------------------------------------------------
def set_meta_styles(args, etree, tstyle):
    lbfo = args.metafo[args.lb_metric]
    if args.lb_metric == 'lbr':  # remove zeroes
        lbfo = {u : (math.log(v) if args.log_lbr else v) for u, v in lbfo.items() if v > 0}
    lbvals = lbfo.values()
    lb_smap = plotting.get_normalized_scalar_map(lbvals, 'viridis')
    lb_min, lb_max = min(lbvals), max(lbvals)

    affyfo = None
    if args.affy_key in args.metafo:
        affyfo = args.metafo[args.affy_key]
        if args.lb_metric == 'lbi':
            affyvals = affyfo.values()
            affy_smap = plotting.get_normalized_scalar_map(affyvals, 'viridis')
        elif args.lb_metric == 'lbr':
            delta_affyvals = set_delta_affinities(etree, affyfo)
            delta_affy_increase_smap = plotting.get_normalized_scalar_map([v for v in delta_affyvals if v > 0], 'Reds', remove_top_end=True) if len(delta_affyvals) > 0 else None
            delta_affy_decrease_smap = plotting.get_normalized_scalar_map([abs(v) for v in delta_affyvals if v < 0], 'Blues', remove_top_end=True) if len(delta_affyvals) > 0 else None
        else:
            assert False

    for node in etree.traverse():
        node.img_style['size'] = 0
        rfsize = 0
        bgcolor = getgrey()
        if args.lb_metric == 'lbi':
            if node.name not in lbfo:  # really shouldn't happen
                print '  %s missing lb info for node \'%s\'' % (utils.color('red', 'warning'), node.name)
                continue
            if affyfo is not None and node.name in affyfo:
                rfsize = get_size(lb_min, lb_max, lbfo[node.name])
                bgcolor = get_color(affy_smap, affyfo, key=node.name)
            else:
                rfsize = 5
                bgcolor = get_color(lb_smap, lbfo, key=node.name)
        elif args.lb_metric == 'lbr':
            node.img_style['vt_line_color'] = getgrey()  # if they're black, it's too hard to see the large changes in affinity, since they're very dark (at least with current color schemes)
            # rfsize = get_size(lb_min, lb_max, lbfo[node.name]) if node.name in lbfo else 1.5
            rfsize = 5 if node.name in lbfo else 1.5
            bgcolor = get_color(lb_smap, lbfo, key=node.name)
            if affyfo is not None and delta_affy_increase_smap is not None and node.affinity_change is not None:
                # tface = ete3.TextFace(('%+.4f' % node.affinity_change) if node.affinity_change != 0 else '0.', fsize=3)
                # node.add_face(tface, column=0)
                if node.affinity_change > 0:  # increase
                    node.img_style['hz_line_color'] = get_color(delta_affy_increase_smap, None, val=node.affinity_change)
                    node.img_style['hz_line_width'] = 1.2
                elif node.affinity_change < 0:  # decrease
                    node.img_style['hz_line_color'] = get_color(delta_affy_decrease_smap, None, val=abs(node.affinity_change))
                    node.img_style['hz_line_width'] = 1.2
                else:
                    node.img_style['hz_line_color'] = getgrey()
        rface = ete3.RectFace(width=rfsize, height=rfsize, bgcolor=bgcolor, fgcolor=None)
        rface.opacity = opacity
        node.add_face(rface, column=0)

    affy_label = args.affy_key.replace('_', ' ')
    if args.lb_metric == 'lbi':
        if affyfo is None:
            add_legend(tstyle, args.lb_metric, lbvals, lb_smap, lbfo, 0, n_entries=4)
        else:
            add_legend(tstyle, args.lb_metric, lbvals, None, lbfo, 0, n_entries=4)
            add_legend(tstyle, affy_label, affyvals, affy_smap, affyfo, 3)
    elif args.lb_metric == 'lbr':
        add_legend(tstyle, args.lb_metric, lbvals, lb_smap, lbfo, 0, reverse_log=args.log_lbr)
        if affyfo is not None:
            add_legend(tstyle, '%s decrease' % affy_label, [abs(v) for v in delta_affyvals if v < 0], delta_affy_decrease_smap, affyfo, 3, add_sign='-', no_opacity=True)
            add_legend(tstyle, '%s increase' % affy_label, [v for v in delta_affyvals if v > 0], delta_affy_increase_smap, affyfo, 6, add_sign='+', no_opacity=True)

# ----------------------------------------------------------------------------------------
def plot_trees(args):
    treefo = read_input(args)

    etree = ete3.Tree(treefo['treestr'], format=1)

    tstyle = ete3.TreeStyle()
    # tstyle.show_scale = False
    # tstyle.scale_length = args.lb_tau
    # tstyle.show_branch_length = True
    # tstyle.complete_branch_lines_when_necessary = True

    if args.metafo is not None:
        set_meta_styles(args, etree, tstyle)

    print '      %s' % args.outfname
    tstyle.show_leaf_name = False
    etree.render(args.outfname, tree_style=tstyle)

# ----------------------------------------------------------------------------------------
parser = argparse.ArgumentParser(formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument('--treefname', required=True)
parser.add_argument('--outfname', required=True)
parser.add_argument('--lb-metric', default='lbi', choices=['lbi', 'lbr'])
parser.add_argument('--affy-key', default='affinity', choices=['affinity', 'relative_affinity'])
# parser.add_argument('--lb-tau', required=True, type=float)
parser.add_argument('--metafname')
parser.add_argument('--partis-dir', default=os.getcwd(), help='path to main partis install dir')
parser.add_argument('--log-lbr', action='store_true')
args = parser.parse_args()

sys.path.insert(1, args.partis_dir + '/python')
try:
    import utils
    import glutils
    import plotting
except ImportError as e:
    print e
    raise Exception('couldn\'t import from main partis dir \'%s\' (set with --partis-dir)' % args.partis_dir)

args.metafo = None
if args.metafname is not None:
    with open(args.metafname) as metafile:
        args.metafo = yaml.load(metafile)

plot_trees(args)
