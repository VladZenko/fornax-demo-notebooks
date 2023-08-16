import pandas as pd
from astroquery.heasarc import Heasarc
from tqdm import tqdm
from astropy.table import Table
import pyvo
import matplotlib.pyplot as plt
import numpy as np

from data_structures import MultiIndexDFObject

#need to know the distribution of error radii for the catalogs of interest
#this will inform the ligh curve query, as we are not intertsted in 
#error radii which are 'too large' so we need a way of defining what that is
def make_hist_error_radii(missioncat):
    """plots a histogram of error radii from a HEASARC catalog
    
    Parameters
    ----------
    missioncat : str 
        single catalog within HEASARC to grab error radii values  Must be one of the catalogs listed here: 
            https://astroquery.readthedocs.io/en/latest/heasarc/heasarc.html#getting-list-of-available-missions
    Returns
    -------
    heasarcresulttable : astropy table
        results of the heasarc search including name, ra, dec, error_radius
        
    """
    # get the pyvo HEASARC service.
    heasarc_tap = pyvo.regsearch(servicetype='tap',keywords=['heasarc'])[0]

    #simple query to select sources from that catalog
    heasarcquery=f"""
        SELECT TOP 5000 cat.name, cat.ra, cat.dec, cat.error_radius
        FROM {missioncat} as cat
         """
    heasarcresult = heasarc_tap.service.run_sync(heasarcquery)

    #  Convert the result to an Astropy Table
    heasarcresulttable = heasarcresult.to_table()

    #make a histogram
    #zoom in on the range of interest
    #error radii are in units of degrees
    plt.hist(heasarcresulttable["error_radius"], bins = 30, range = [0, 10])
    
    #in case anyone wants to look further at the data
    return heasarcresulttable
    
#example calling sequences
#resulttable = make_hist_error_radii('FERMIGTRIG')
#resulttable = make_hist_error_radii('SAXGRBMGRB')

def make_VOTable(coords_list, labels_list, sourcefilename):
    """convert the coords and labels into a VOTable for input to ADQL catalog search
    
    Parameters
    ----------
    coords_list : list of astropy skycoords
        the coordinates of the targets for which a user wants light curves
    labels_list: list of strings
        journal articles associated with the target coordinates
    sourcefilename: str
        name of the output file; must be .xml
    """
    
    tab = Table({
        'name': labels_list,
        'ra': [coord.ra for objectid, coord in coords_list],
        'dec': [coord.dec for objectid, coord in coords_list],
        'ID': [objectid for objectid, coord in coords_list]
    })
    #write out to an .xml file
    tab.write(sourcefilename, format='votable', overwrite=True)
    
    return sourcefilename

def HEASARC_get_lightcurves(heasarc_cat, max_error_radius, xml_filename):
    """Searches HEASARC archive for light curves from a specific list of mission catalogs
    
    Parameters
    ----------
    heasarc_cat : str list
        list of catalogs within HEASARC to search for light curves.  Must be one of the catalogs listed here: 
            https://astroquery.readthedocs.io/en/latest/heasarc/heasarc.html#getting-list-of-available-missions
    max_error_radius : flt list
        maximum error radius to include in the returned catalog of objects 
        ie., we are not interested in GRBs with a 90degree error radius because they will fit all of our objects
    xml_filename: str
        filename which has the list of sources to cross match with HEASARC catalogs
        must be  a VOTable in xml format
        generated by `make_VOTable` functiom
        
    Returns
    -------
    df_lc : MultiIndexDFObject
        the main data structure to store all light curves
    """

    #setup to store the data
    df_lc = MultiIndexDFObject()

    # get the pyvo HEASARC service.
    heasarc_tap = pyvo.regsearch(servicetype='tap',keywords=['heasarc'])[0]

    #Fermi:
    # create the query for FERMIGTRIG, searching for the sources defined in sources.xml from HEASARC_make_VOTable;
    # Note that the sources.xml file is uploaded when we run the query with run_sync
    
    for m in tqdm(range(len(heasarc_cat))):    
        print('working on mission', heasarc_cat[m])

        fermiquery=f"""
            SELECT cat.name, cat.ra, cat.dec, cat.error_radius, cat.time,  mt.ID, mt.name
            FROM {heasarc_cat[m]} cat, tap_upload.mytable mt
            WHERE
            cat.error_radius < {max_error_radius[m]} AND
            CONTAINS(POINT('ICRS',mt.ra,mt.dec),CIRCLE('ICRS',cat.ra,cat.dec,cat.error_radius))=1
             """
        fermiresult = heasarc_tap.service.run_sync(fermiquery, uploads={'mytable': xml_filename})

        #  Convert the result to an Astropy Table
        fermiresulttable = fermiresult.to_table()

        #add results to multiindex_df
        #really just need to mark this spot with a vertical line in the plot, it's not actually a light curve
        #so making up a flux and an error, but the time stamp and mission are the real variables we want to keep
        df_fermi = pd.DataFrame(dict(flux=np.full(len(fermiresulttable),0.1), err=np.full(len(fermiresulttable),0.1), time=fermiresulttable['time'], objectid = fermiresulttable['id'], band=np.full(len(fermiresulttable),'Fermi GRB'), label=fermiresulttable['name2'])).set_index(["objectid", "label", "band", "time"])

        # Append to existing MultiIndex light curve object
        df_lc.append(df_fermi)
    
    return df_lc

def HEASARC_get_lightcurves_forloop(coords_list,labels_list,radius, mission_list ):
    """Searches HEASARC archive for light curves from a specific list of mission catalogs
    This search happens with astroquery, one object at a time.
    This search is deprecated in favor of HEASARC_get_lightcurves which uses a TAP query crossmatch
    
    Parameters
    ----------
    coords_list : list of astropy skycoords
        the coordinates of the targets for which a user wants light curves
    labels_list: list of strings
        journal articles associated with the target coordinates
    radius : astropy.units.quantity.Quantity
        search radius, how far from the source should the archives return results
    mission_list : str list
        list of catalogs within HEASARC to search for light curves.  Must be one of the catalogs listed here: 
            https://astroquery.readthedocs.io/en/latest/heasarc/heasarc.html#getting-list-of-available-missions
    Returns
    -------
    df_lc : MultiIndexDFObject
        the main data structure to store all light curves
    """
    
    #for the yang sample, no results are returned, so this is an example that will return a result for testing
    #for ccount in range(1):
        #To get a fermigtrig source
        #coord = SkyCoord('03h41m21.2s -89d00m33.0s', frame='icrs')

        #to get a bepposax source
        #coord = SkyCoord('14h32m00.0s -88d00m00.0s', frame='icrs')

    df_lc = MultiIndexDFObject()
    for objectid, coord in tqdm(coords_list):
        #use astroquery to search that position for either a Fermi or Beppo Sax trigger
        for mcount, mission in enumerate(mission_list):
            try:
                results = Heasarc.query_region(coord, mission = mission, radius = radius)#, sortvar = 'SEARCH_OFFSET_')
                #really just need to save the one time of the Gamma ray detection
                #time is already in MJD for both catalogs
                if mission == 'FERMIGTRIG':
                    time_mjd = results['TRIGGER_TIME'][0].astype(float)
                else:
                    time_mjd = results['TIME'][0].astype(float)
                
                type(time_mjd)
                lab = labels_list[objectid]

                #really just need to mark this spot with a vertical line in the plot
                dfsingle = pd.DataFrame(dict(flux=[0.1], err=[0.1], time=[time_mjd], objectid=[objectid], band=[mission], label=lab)).set_index(["objectid", "label", "band", "time"])

                # Append to existing MultiIndex light curve object
                df_lc.append(dfsingle)

            except AttributeError:
            #print("no results at that location for ", mission)
                pass
            
    return df_lc

#**** These HEASARC searches are returning an attribute error because of an astroquery bug
# bug submitted to astroquery Oct 18, waiting for a fix.
# if that gets fixed, can probably change this cell 
