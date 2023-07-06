"""
This module provides a function to create surfaces, which includes the marching
cube algorithm, optional topology fixing, and remeshing and smoothing.

"""

# ------------------------------------------------------------------------------
# main function

def createSurface(params):

    """

    """

    # imports

    import os
    import sys
    import shutil
    import subprocess
    import pyacvd

    import numpy as np
    import nibabel as nb
    import pyvista as pv

    from lapy import TriaMesh
    from scipy import sparse as sp
    from scipy import ndimage as nd
    from skimage import measure as skm

    # message

    print()
    print("-------------------------------------------------------------------------")
    print()
    print("Creating surface via marching cube algorithm")
    print()
    print("-------------------------------------------------------------------------")
    print()

    # create surface via marching cube algorithm

    if params.internal.MCA == "mri_mc":

        cmd = os.path.join(os.environ.get('FREESURFER_HOME'), "bin", "mri_mc") + " " \
            + os.path.join(params.OUTDIR, params.HEMI + "." + params.internal.HSFLABEL_02 + ".mgz") \
            + " 1 " \
            + os.path.join(params.OUTDIR, params.HEMI + ".mc." + params.internal.HSFLABEL_02 + ".vtk") + " " \
            + str(params.internal.MCC)

        print(cmd)

        subprocess.run(cmd.split())

    elif params.internal.MCA == "mri_tessellate":

        cmd = os.path.join(os.environ.get('FREESURFER_HOME'), "bin", "mri_pretess") + " " \
            + os.path.join(params.OUTDIR, params.HEMI + "." + params.internal.HSFLABEL_02 + ".mgz") \
            + " xyz " \
            + os.path.join(params.OUTDIR, params.HEMI + "." + params.internal.HSFLABEL_02 + ".mgz") \
            + " " \
            + os.path.join(params.OUTDIR, params.HEMI + ".pt." + params.internal.HSFLABEL_02 + ".mgz")

        print(cmd)

        subprocess.run(cmd.split())

        cmd = os.path.join(os.environ.get('FREESURFER_HOME'), "bin", "mri_tessellate") + " " \
            + os.path.join(params.OUTDIR, params.HEMI + ".pt." + params.internal.HSFLABEL_02 + ".mgz") \
            + " 1 " \
            + os.path.join(params.OUTDIR, params.HEMI + ".mc." + params.internal.HSFLABEL_02 + ".fsmesh")

        print(cmd)

        subprocess.run(cmd.split())

        # convert from freesurfer binary surface format to vtk

        cmd = os.path.join(os.environ.get('FREESURFER_HOME'), "bin", "mris_convert") + " " \
            + os.path.join(params.OUTDIR, params.HEMI + ".mc." + params.internal.HSFLABEL_02 + ".fsmesh") + " " \
            + os.path.join(params.OUTDIR, params.HEMI + ".mc." + params.internal.HSFLABEL_02 + ".vtk")

        print(cmd)

        subprocess.run(cmd.split())

    elif params.internal.MCA == "skimage":

        img = nb.load(os.path.join(params.OUTDIR, params.HEMI + "." + params.internal.HSFLABEL_02 + ".mgz"))
        dat = img.get_fdata()

        msh = skm.marching_cubes(dat)

        v = np.matmul(img.header.get_vox2ras_tkr(), np.concatenate((msh[0], np.ones((msh[0].shape[0],1))), axis=1).T).T[:, 0:3]
        t = msh[1]

        TriaMesh(v, t).write_vtk(os.path.join(params.OUTDIR, params.HEMI + ".mc." + params.internal.HSFLABEL_02 + ".vtk"))

    # update params

    params.internal.HSFLABEL_03 = "mc."+params.internal.HSFLABEL_02
    params.internal.HSFLABEL_04 = params.internal.HSFLABEL_03
    params.internal.HSFLABEL_05 = params.internal.HSFLABEL_04

    # message

    print()
    print("-------------------------------------------------------------------------")
    print()
    print("Smooth surface")
    print()
    print("-------------------------------------------------------------------------")
    print()

    # remesh

    if params.internal.REMESH is not None:

        if shutil.which("mris_remesh") is None:

            Mesh = pv.PolyData(os.path.join(params.OUTDIR, params.HEMI + "." + params.internal.HSFLABEL_05 + ".vtk"))

            clustered = pyacvd.Clustering(Mesh)
            clustered.subdivide(4)
            clustered.cluster(Mesh.n_points)

            remeshed = clustered.create_mesh()

            vr = remeshed.points
            tr = np.reshape(remeshed.faces, (int(len(remeshed.faces)/4), 4))[:,1:]

            # check remesh results

            # creates list of edges
            trSort = np.sort(tr, axis=1)
            trSortEdges = np.concatenate((trSort[:,[0,1]],  trSort[:,[1,2]], trSort[:,[0,2]]), axis=0)

            # remove trias that have an edge that only occurs once (boundary trias)
            countEdges = np.unique(trSortEdges, axis=0, return_counts=True)
            removeEdges = countEdges[0][np.where(countEdges[1]==1)[0]]
            if len(removeEdges)>0:
                removeTrias = np.unique([ np.where(np.sum(np.logical_or(trSort==i[0], trSort==i[1]), axis=1)==2)[0] for i in removeEdges ])
                trSortRmBnd = np.delete(trSort, removeTrias, axis=0)
            else:
                trSortRmBnd = trSort.copy()

            # assure that any edge occurs exactly two times (duplicates)
            trSortRmBndEdges = np.concatenate((trSortRmBnd[:,[0,1]],  trSortRmBnd[:,[1,2]], trSortRmBnd[:,[0,2]]), axis=0)
            if len(np.where(np.unique(trSortRmBndEdges, axis=0, return_counts=True)[1]!=2)[0])!=0:
                print("Duplicate edges in mesh, exiting.")
                sys.exit(1)

            # assure that every edge must be part of exactly two different triangles (no boundary edges, no duplicates)
            countEdgesInTrias = np.array([ np.sum(np.sum(np.logical_or(trSortRmBnd==trSortRmBndEdges[i,0], trSortRmBnd==trSortRmBndEdges[i,1]), axis=1)==2) for i in range(0, len(trSortRmBndEdges)) ])
            if (countEdgesInTrias!=2).any():
                print("Boundary or duplicate edges in mesh, exiting.")
                sys.exit(1)

            # restrict to largest connected component

            triaMesh = TriaMesh(v=vr, t=trSortRmBnd)
            comps = sp.csgraph.connected_components(triaMesh.adj_sym, directed=False)
            if comps[0]>1:
                compsLargest = np.argmax(np.unique(comps[1], return_counts=True)[1])
                vtcsRemove = np.where(comps[1]!=compsLargest)
                triaKeep = np.sum(np.isin(trSortRmBnd, vtcsRemove), axis=1)==0
                trSortRmBndRmComps = trSortRmBnd[triaKeep,:]
            else:
                trSortRmBndRmComps = trSortRmBnd

            # remove free vertices and re-orient mesh

            triaMesh = TriaMesh(v=vr, t=trSortRmBndRmComps)
            triaMesh.rm_free_vertices_()
            triaMesh.orient_()

        else:

            if params.internal.REMESH == 0:
                cmd = os.path.join(os.environ.get('FREESURFER_HOME'), "bin", "mris_remesh") + " " \
                    + "--remesh  -i " + os.path.join(params.OUTDIR, params.HEMI + "." + params.internal.HSFLABEL_05 + ".vtk") + " " \
                    + "-o " + os.path.join(params.OUTDIR, params.HEMI + ".rm." + params.internal.HSFLABEL_05 + ".vtk")
            elif params.internal.REMESH > 0:
                cmd = os.path.join(os.environ.get('FREESURFER_HOME'), "bin", "mris_remesh") + " " \
                    + "--nvert " + str(params.internal.REMESH) + "  -i " + os.path.join(params.OUTDIR, params.HEMI + "." + params.internal.HSFLABEL_05 + ".vtk") + " " \
                    + "-o " + os.path.join(params.OUTDIR, params.HEMI + ".rm." + params.internal.HSFLABEL_05 + ".vtk")

            print(cmd)

            subprocess.run(cmd.split())

            # remove free vertices and re-orient mesh

            triaMesh = TriaMesh.read_vtk(os.path.join(params.OUTDIR, params.HEMI + ".rm." + params.internal.HSFLABEL_05 + ".vtk"))
            triaMesh.rm_free_vertices_()
            triaMesh.orient_()

    else:

        # remove free vertices and re-orient mesh

        triaMesh = TriaMesh.read_vtk(os.path.join(params.OUTDIR, params.HEMI + "." + params.internal.HSFLABEL_05 + ".vtk"))
        triaMesh.rm_free_vertices_()
        triaMesh.orient_()

    # save

    TriaMesh.write_vtk(triaMesh, os.path.join(params.OUTDIR, params.HEMI + ".rm." + params.internal.HSFLABEL_05 + ".vtk"))

    # smoothing

    triaMesh = TriaMesh.read_vtk(os.path.join(params.OUTDIR, params.HEMI + ".rm." + params.internal.HSFLABEL_05 + ".vtk"))

    triaMesh.smooth_(n=params.internal.SMO)

    TriaMesh.write_vtk(triaMesh, os.path.join(params.OUTDIR, params.HEMI + ".rs." + params.internal.HSFLABEL_05 + ".vtk"))

    # update HSFLABEL 6

    params.internal.HSFLABEL_06 = "rs." + params.internal.HSFLABEL_05

    # return

    return(params)
