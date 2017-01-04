import sys
import glob
import time
import operator
from subprocess import check_call
import copy
import os

import utils
import plotting
from hist import Hist

# ----------------------------------------------------------------------------------------
class AlleleRemover(object):
    def __init__(self, glfo, args, alfinder):
        self.glfo = glfo
        self.args = args
        self.alfinder = alfinder

        # self.n_five_prime_positions_to_exclude = 2  # skip positions that are too close to the 5' end of V (depending on sequence method, these can be unreliable. uh, I think?)
        # self.n_three_prime_positions_to_exclude = 4  # skip positions that are too close to the 3' end of V (misassigned insertions look like snps)
        # self.n_bins = 30
        # self.xmin, self.xmax = 0., 1.
        # self.counts = {}

        self.genes_to_keep = None
        self.genes_to_remove = None
        self.dbg_strings = {}
        self.region = 'v'
        self.codon_positions = self.glfo[utils.conserved_codons[self.glfo['chain']][self.region] + '-positions']

        self.finalized = False

    # ----------------------------------------------------------------------------------------
    def increment(self, qinfo, line_info, debug=False):
        return
        # for region in ['v', ]:
        #     best_gene = line_info[region + '_gene']
        #     best_hfrac = None
        #     second_closest_gene, second_smallest_hfrac = None, None  # NOTE I'm not actually positive that the best s-w match has the smallest hfrac, but I don't really care, either
        #     for score, gene in qinfo['matches'][region]:
        #         germline_seq = self.glfo['seqs'][region][gene][qinfo['glbounds'][gene][0] : qinfo['glbounds'][gene][1]]
        #         assert len(line_info['seqs']) == 1
        #         query_seq = line_info['seqs'][0][qinfo['qrbounds'][gene][0] : qinfo['qrbounds'][gene][1]]  # NOTE this means we're in general using different length matches for each gene, but it seems the least bad thing to do, at least a.t.m.
        #         assert len(germline_seq) == len(query_seq)

        #         germline_seq = germline_seq[self.n_five_prime_positions_to_exclude : -self.n_three_prime_positions_to_exclude]
        #         query_seq = query_seq[self.n_five_prime_positions_to_exclude : -self.n_three_prime_positions_to_exclude]
        #         hfrac = utils.hamming_fraction(germline_seq, query_seq)

        #         # print '    %5d  %3d / %3d = %5.3f %s' % (score, utils.hamming_distance(germline_seq, query_seq), len(germline_seq), hfrac, gene)

        #         if gene == best_gene:
        #             best_hfrac = hfrac
        #             continue

        #         if second_smallest_hfrac is None or hfrac < second_smallest_hfrac:
        #             second_smallest_hfrac = hfrac
        #             second_closest_gene = gene

        #     if second_smallest_hfrac is None:
        #         print '    no other matches for ', line_info['unique_ids'][0]
        #         if len(qinfo['matches'][region]) > 1:
        #                raise Exception(line_info['unique_ids'][0])
        #         return

        #     if debug:
        #         print 'best %.3f   second %.3f' % (best_hfrac, second_smallest_hfrac)

        #     if best_gene not in self.counts:
        #         self.counts[best_gene] = {'best' : Hist(self.n_bins, self.xmin, self.xmax, title='best'), 'second' : Hist(self.n_bins, self.xmin, self.xmax, title='second')}
        #     self.counts[best_gene]['best'].fill(best_hfrac)
        #     self.counts[best_gene]['second'].fill(second_smallest_hfrac)

    # ----------------------------------------------------------------------------------------
    def separate_into_classes(self, sorted_gene_counts, easycounts):
        class_counts = []
        for gene, counts in sorted_gene_counts:
            seq = self.glfo['seqs'][self.region][gene][:self.codon_positions[gene] + 3]
            add_new_class = True
            for gclass in class_counts:
                for gfo in gclass:
                    if len(gfo['seq']) != len(seq):
                        continue
                    hdist = utils.hamming_distance(gfo['seq'], seq)
                    if hdist < self.args.n_max_snps - 1:  # if this gene is close to any gene in the class, add it to this class
                        add_new_class = False
                        class_counts[class_counts.index(gclass)].append({'gene' : gene, 'counts' : counts, 'seq' : seq})
                        break
                if not add_new_class:
                    break

            if add_new_class:
                class_counts.append([{'gene' : gene, 'counts' : counts, 'seq' : seq}, ])

        return class_counts

    # ----------------------------------------------------------------------------------------
    def keep_this_gene(self, this_gene, pcounter, easycounts, debug=False):
        assert self.region == 'v'  # conserved codon stuff below will have to be changed for j
        glseqs = self.glfo['seqs'][self.region]
        this_seq = glseqs[this_gene][:self.codon_positions[this_gene] + 3]  # only compare up to the conserved cysteine

        # don't keep it if it's pretty close to a gene we already have
        n_close_genes = 0
        nearest_gene, nearest_hdist = None, None
        for kgene in self.genes_to_keep:
            kseq = glseqs[kgene][:self.codon_positions[kgene] + 3]
            if len(kseq) != len(this_seq):
                continue
            hdist = utils.hamming_distance(kseq, this_seq)
            if nearest_hdist is None or hdist < nearest_hdist:
                nearest_hdist = hdist
                nearest_gene = kgene
            if hdist < self.args.n_max_snps - 1:
                n_close_genes += 1

        if easycounts[this_gene] < self.alfinder.n_total_min:  # if we hardly ever saw it, there's no good reason to believe it wasn't the result of just mutational wandering
            self.dbg_strings[this_gene] = 'not enough counts (%d < %d)' % (easycounts[this_gene], self.alfinder.n_total_min)
            return False

        self.dbg_strings[this_gene] = 'nearest gene %s %s' % (nearest_gene, nearest_hdist)
        return True

    # ----------------------------------------------------------------------------------------
    def finalize(self, pcounter, swfo, debug=False):
        assert not self.finalized
        sorted_gene_counts = [(deps[0], counts) for deps, counts in sorted(pcounter.counts[self.region + '_gene'].items(), key=operator.itemgetter(1), reverse=True)]
        easycounts = {gene : counts for gene, counts in sorted_gene_counts}
        total_counts = sum([counts for counts in easycounts.values()])

        self.genes_to_keep = set()

        if debug:
            print '  removing least likely alleles (%d total counts)' % total_counts
            print '     %-20s    %5s (%s)      removed counts     removed genes' % ('genes to keep', 'counts', 'snps'),

        class_counts = self.separate_into_classes(sorted_gene_counts, easycounts)
        for iclass in range(len(class_counts)):
            gclass = class_counts[iclass]
            n_from_this_class = 0
            for ig in range(len(gclass)):
                gfo = gclass[ig]
                if self.args.n_max_total_alleles is not None and len(self.genes_to_keep) >= self.args.n_max_total_alleles:  # command line can specify the total number of alleles
                    break

                if float(gfo['counts']) / total_counts < self.args.min_allele_prevalence_fraction:  # always skip everybody that's super uncommon
                    pass
                elif ig == 0:  # keep the first one from this class
                    self.genes_to_keep.add(gfo['gene'])
                    n_from_this_class += 1
                elif utils.hamming_distance(gclass[0]['seq'], gclass[ig]['seq']) == 0:  # don't keep it if it's indistinguishable from the most common one (the matches are probably mostly really the best one)
                    pass  # don't keep it
                elif n_from_this_class < self.args.n_alleles_per_gene:  # always keep the most common <self.args.n_alleles_per_gene> in each class
                    self.genes_to_keep.add(gfo['gene'])
                    n_from_this_class += 1
                else:
                    pass  # don't keep it

                if debug:
                    snpstr = ' ' if ig == 0 else '(%d)' % utils.hamming_distance(gclass[0]['seq'], gfo['seq'])
                    # keepstr = utils.color('yellow', 'x', width=5) if gfo['gene'] in self.genes_to_keep else '     '
                    if gfo['gene'] in self.genes_to_keep:
                        print '\n       %-s  %5d  %-3s' % (utils.color_gene(gfo['gene'], width=20), gfo['counts'], snpstr),
            if n_from_this_class == 0:
                print '\n       %-s  %5s  %-3s' % (utils.color('blue', 'none', width=20, padside='right'), '-', ''),
            if debug:
                print '           %5d            %s' % (sum([gfo['counts'] for gfo in gclass]), ' '.join([utils.color_gene(gfo['gene']) for gfo in gclass])),
        if debug:
            print ''

        # for igene in range(len(sorted_gene_counts)):
        #     gene, counts = sorted_gene_counts[igene]
        #     if igene == 0:  # always keep the first one
        #         self.dbg_strings[gene] = 'first gene'
        #         self.genes_to_keep.add(gene)
        #         continue
        #     if self.keep_this_gene(gene, pcounter, easycounts, debug=debug):
        #         self.genes_to_keep.add(gene)

        # print '  keeping:'
        # for gene in [g for g, _ in sorted_gene_counts if g in self.genes_to_keep]:
        #     print '    %5d  %s  %s' % (easycounts[gene], utils.color_gene(gene, width=15), self.dbg_strings[gene])

        self.genes_to_remove = set(self.glfo['seqs'][self.region]) - self.genes_to_keep

        # print '  removing:'
        # for gene in [g for g, _ in sorted_gene_counts if g in self.genes_to_remove]:
        #     print '    %5d  %s  %s' % (easycounts[gene], utils.color_gene(gene, width=15), self.dbg_strings[gene])

        n_queries_with_removed_genes = 0
        for query in swfo['queries']:
            line = swfo[query]
            if line[self.region + '_gene'] in self.genes_to_remove:
                n_queries_with_removed_genes += 1
                # unpadded_line = copy.deepcopy(line)
                # unpadded_line['seqs'][0] = unpadded_line['seqs'][0][unpadded_line['padlefts'][0] : ]
                # if unpadded_line['padrights'][0] > 0:
                #     unpadded_line['seqs'][0] = unpadded_line['seqs'][0][ : -unpadded_line['padrights'][0]]
                # utils.print_reco_event(self.glfo['seqs'], unpadded_line)

        print '    keeping %d %s genes' % (len(self.genes_to_keep), self.region)
        print '    removing %d %s genes: %d with no matches, %d with unconvincing matches (%d / %d queries had their best match removed)' % (len(self.genes_to_remove), self.region, len(set(self.glfo['seqs'][self.region]) - set(easycounts)), len(set(easycounts) - self.genes_to_keep), n_queries_with_removed_genes, len(swfo['queries']))

        self.finalized = True

    # ----------------------------------------------------------------------------------------
    def plot(self, base_plotdir, only_csv=False):
        return
        # if not self.finalized:
        #     self.finalize(debug=debug)

        # print '    plotting'
        # plotdir = base_plotdir + '/allele-removing'

        # utils.prep_dir(plotdir, wildlings=('*.csv', '*.svg'))

        # if only_csv:  # not implemented
        #     print '    only_csv not yet implemented in allelefinder'
        #     return

        # start = time.time()
        # for gene, hists in self.counts.items():
        #     plotting.draw_no_root(hists['best'], plotname=utils.sanitize_name(gene), plotdir=plotdir, more_hists=[hists['second'], ], errors=True, plottitle=gene, xtitle='mut freq', ytitle='counts', linewidths=[5, 3])

        # plotting.make_html(plotdir)
        # check_call(['./bin/permissify-www', plotdir])
        # print '      allele removing plot time: %.1f' % (time.time()-start)
