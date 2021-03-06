#!/usr/bin/env python
# :noTabs=true:

"""
Methods for preparing input for PSIBLAST (sequence file), running PSIBLAST,
and parsing the output PSSM

Note: the run options for PSIBLAST are setup in run_psiblast and set in
settings.py in PSIBLAST_OPTIONS
"""

################################################################################
# IMPORT

# common modules
import os
import re

# bigger modules

# custom modules
from vipur_settings import AMINO_ACID_CODES , PATH_TO_PSIBLAST , PSIBLAST_OPTIONS , PROTEIN_LETTERS
from helper_methods import create_executable_str , run_local_commandline

################################################################################
# METHODS

# for sequence searches
def extract_protein_sequence_from_pdb( pdb_filename , out_filename = '' , target_chain = 'A' , write_numbering_map = True ):
    """
    Returns the protein sequence found in  <pdb_filename>  matching
    <target_chain>  and writes the sequence (in FASTA format) to  <out_filename>
    
    Optionally  <write_numbering_map>  that maps the PDB residue numbering to
        the sequence (0-indexed) numbering*
    
    Note: although the sequence file is only required for input to PSIBLAST,
        the sequence and residue numbering map are useful for identifying
        improper/malformed variant inputs

    *Note: since many protein structures (in PDB format) map to only a region
        of the protein of interest, VIPUR will often be run only on this region
        the  <residue_map>  ensures the actual protein positions are maintained
        during analysis (since many of these programs would consider the start
        of the modeled region as the first residue in the protein)
    """
    # default output
    root_filename = pdb_filename.rstrip( '.pdb' )
    if not out_filename:
        out_filename = root_filename + '.fa'

    # load the ATOM lines
    f = open( pdb_filename , 'r' )
    lines = [i for i in f.xreadlines() if i[:4] == 'ATOM']
    f.close()
        
    sequence = ''
    residues = []
    last_resi = None
    for i in lines:
        if not i[21:22] == target_chain:
            continue
        
        resi = i[22:27].strip()
        if not resi == last_resi:
            # a new residue, add the amino acid
            sequence += AMINO_ACID_CODES[i[17:20]]
            residues.append( resi )
            last_resi = resi
    
    print 'extracted protein sequence from ' + pdb_filename + ' chain ' + target_chain
        
    # optionally write the numbering map
    if write_numbering_map:
        # allow it to be a str
        if isinstance( write_numbering_map , str ):
            numbering_map_filename = write_numbering_map
        else:
            numbering_map_filename = pdb_filename.rstrip( '.pdb' ) + '.numbering_map'

        f = open( numbering_map_filename , 'w' )
        f.write( '\n'.join( ['\t'.join( [residues[i] , str( i ) , sequence[i]] ) for i in xrange( len( residues ) )] ) )
        f.close()

        print 'wrote the numbering for ' + pdb_filename + ' chain ' + target_chain + ' to ' + numbering_map_filename
    
    # convert into a dict
    residues = dict( [(residues[i] , i) for i in xrange( len( residues ) )] )

    # "optionally" write out the sequence
    # currently a default, not an option - will determine an appropriate  <out_filename>  if not provided as an argument
    if out_filename:
        # write it to output directory
        f = open( out_filename , 'w' )
        f.write( '>' + root_filename +'_chain_'+ target_chain +'\n'+ sequence )
        f.close()
        print 'wrote the sequence for ' + pdb_filename + ' chain ' + target_chain + ' to ' + out_filename

    return sequence , residues , out_filename

# need to support this, preprocessing -> run
def load_numbering_map( numbering_map_filename ):
    f = open( numbering_map_filename , 'r' )
    residues = [i.strip( '\n' ).split( '\t' ) for i in f.xreadlines()]
    f.close()
    
    residues = dict( [(i[0] , i[1]) for i in residues] )
    # make floats? seems like str before anyway
    
    return residues

# contingency method used if run in "sequence only" mode
def load_fasta( fasta_filename ):
    f = open( fasta_filename , 'r' )
    lines = f.readlines()
    f.close()
    
    sequences = []
    for i in lines:
        if i[0] == '>':
            sequences.append( [i.lstrip( '>' ) , ''] )
        else:
            sequences[-1][1] += i.strip()    # remove other characters
    
    # summarize mutliple sequences?
    return sequences

# local
def run_psiblast( sequence_filename , run = True ):
    """
    Runs PSIBLAST on  <sequence_filename>  using the default options in
    PSIBLAST_OPTIONS and returns the relevant output file: "out_ascii_pssm"
    """
    root_filename = os.path.abspath( sequence_filename ).rstrip( '.fa' )
    
    # collect the options, set the input, derive the output filenames
    psiblast_options = {}
    psiblast_options.update( PSIBLAST_OPTIONS )
    psiblast_options['query'] = sequence_filename
    for i in psiblast_options.keys():
        if '__call__' in dir( psiblast_options[i] ):
            psiblast_options[i] = psiblast_options[i]( root_filename )

    for i in psiblast_options.keys():
        if isinstance( psiblast_options[i] , str ) and os.path.isfile( psiblast_options[i] ):
            psiblast_options[i] = os.path.abspath( psiblast_options[i] )
    
    command = create_executable_str( PATH_TO_PSIBLAST , args = [] , options = psiblast_options )

    if run:
        run_local_commandline( command )
    
        # the only output we need
        return psiblast_options['out_ascii_pssm']
    else:
        # just send the command
        return command , psiblast_options['out_ascii_pssm']

# simple method, scan for empty/non-existent pssm + if "no hits" were found
def check_psiblast_output( psiblast_pssm , psiblast_output = None , failed_output_str = 'No hits found' ):
    # well, if the pssm file is NOT empty, things are good
    # if it is empty, check the psiblast_output for "No hits found"
    not_empty = None
    success = True
    
    if os.path.isfile( psiblast_pssm ):
        f = open( psiblast_pssm , 'r' )
        not_empty = bool( f.read().strip() )
        f.close()
    if not not_empty:
        # pssm does not exist OR was empty
        if not os.path.isfile( psiblast_output ):
            # both files empty or missing
            success = False
        else:
            f = open( psiblast_output , 'r' )
            lines = f.read()
            f.close()
            
            if failed_output_str.lower() in lines.lower():
                not_empty = False
                # but successful, just empty
            else:
                # major problems, both failed to generate
                # OR empty but also not supposed to be, rerun
                success = False
            
    return success , not_empty

# modified by njc, hybrid method
# now robust to versions, based on separator rather than anticipated structure
def extract_pssm_from_psiblast_pssm( pssm_filename , aa_line_shift = -4 , columns = len( PROTEIN_LETTERS ) ):
    # most args are ignored---left for backward compatibility.

    # fields can be separated by spaces and perhaps a '-' sign, or in some cases just a '-' sign.
    #
    # note: this re captures, so we will be given each field's separator. we need this to restore
    # '-' signs.
    split_line = re.compile( '( +-?|-)' )

    f = open( pssm_filename , 'r' )
    lines = [i.rstrip( '\n' ) for i in f.xreadlines()]
    f.close()

    split_lines = []
    for line in lines:
        ff = split_line.split( line )
        if not ff[0]:
            ff.pop( 0 )    # re splits include a dummy empty field if the first field
                           # begins with a separator. (so drop it)
        ff = [sep[-1] + dat for sep , dat in zip( ff[::2] , ff[1::2] )]    # restore the separators to each field.
        # only care about "-" character if its there
        split_lines.append( ff )

    # HACK: assume lines with data have the largest number of columns.
    most_columns = max( [len( ff ) for ff in split_lines] )

    # line listing amino acids has four fewer columns: it is missing position, query, information,
    # and relative weight fields. there should be one and only one such line.
    aa_line = [ff for ff in split_lines if len( ff ) == most_columns + aa_line_shift]
    assert len( aa_line ) == 1
    aa_line = aa_line[0]
    
    # build a map from column index to aa, then run some sanity checks. note the line lists each aa twice.
    x2aa = dict( [(x , aa.strip()) for x , aa in enumerate( aa_line )] )
    num_aa = len( x2aa )/2
    assert num_aa*2 == len( x2aa )
    assert num_aa == columns    # sanity check
    assert not [x for x in xrange( num_aa ) if not x2aa[x] == x2aa[x + num_aa]]

    pssm_dict = {}
    for ff in split_lines:
        if not len( ff ) == most_columns: continue
        pos = int( ff[0] )
        pssm_dict[pos] = {
            'position':                pos ,
            'query identity':          ff[1] ,
            'log-likelihood':          dict( [(x2aa[x] , int(v)) for x , v in enumerate( ff[2:2 + num_aa] )] ) ,
            'approximate frequencies': dict( [(x2aa[x] , float(v)/100) for x , v in enumerate( ff[2+num_aa:2 + 2*num_aa] )] ) ,
            'information content':     float( ff[-2] ) ,
            '?':                       float( ff[-1] ) ,
        }
    #DEBUG pssm_dict['XTRA_AALINE'] = aaline
    return pssm_dict


