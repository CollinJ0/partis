#ifndef JOB_HOLDER_H
#define JOB_HOLDER_H

#include <map>
#include <string>
#include "StochHMMlib.h"
#include "StochHMM_usage.h"
#include "germlines.h"

using namespace std;
using namespace StochHMM;

typedef pair<size_t,size_t> KSet;  // pair of k_v,k_d values specifying how to chop up the query sequence into v+insert, d+insert, j

// ----------------------------------------------------------------------------------------
class JobHolder {
public:
  JobHolder(string hmmtype, string algorithm, string hmm_dir, string seqfname, size_t n_max_versions=0);
  ~JobHolder();
  void Run(size_t k_v_start, size_t n_k_v, size_t k_d_start, size_t n_k_d);
  void FillTrellis(model *hmm, sequences *query_seqs, string region, string gene);
  void PrintPath(string query_str, string gene);
  void RunKSet(KSet kset);

private:
  map<string,sequences> GetSubSeqs(size_t k_v, size_t k_d);  // get the subsequences for the v, d, and j regions given a k_v and k_d
  size_t GetInsertLength(vector<string> labels);
  size_t GetErosionLength(string side, vector<string> path_labels, string gene_name);

  string hmm_dir_;  // location of .hmm files
  size_t n_max_versions_;    // only look at the first n gene versions (speeds things up for testing)
  string algorithm_;
  GermLines gl_;
  vector<string> regions_;
  track track_;
  sequences seqs_;
  map<KSet,double> scores_;  // map from kset to total score for that kset
  map<string, map<string,trellis*> > trellisi_;  // collection of the trellises we've calculated, so we can reuse them. eg: trellisi_["IGHV1-18*01"]["ACGGGTCG"]
  map<string, map<string,traceback_path*> > paths_;  // collection of the paths. 
  vector<string>::iterator i_current_region_;  // region and position of the *next* job we will pass out with GetNextJob()
  vector<string>::iterator i_current_gene_;
};
#endif
