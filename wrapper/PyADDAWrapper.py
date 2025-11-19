import subprocess
import os
import re
import numpy as np
import csv
import time
import pandas as pd
from tkinter import Tk
from tkinter.filedialog import askopenfilename
from refractiveindex import RefractiveIndexMaterial as nMat

#Multithread execution
from threading import Thread
from queue import Queue
from concurrent.futures import ThreadPoolExecutor

Tk().withdraw()
adda_file = os.path.splitext(askopenfilename(defaultextension='.exe', filetypes=[('Executables', '.exe')], title='Choose path to adda.exe', ))[0]
adda_folder = os.path.split(adda_file)

#spectrum calculation
def adda_spectrum(
    addaFolder = adda_file,
    shape="ellipsoid", #TODO: implement other shapes
    wavelength=500, #wavelength of the incoming light in nm
    radius=20, #Radius of the particle in nm
    nPart=1.5 + 0.2j, #RI of the particles
    euler = (0, 0, 0), #euler angles
    granulRI = 1.4 + 0.1j, #RI of the internal granules
    nMedium=1.333, #RI of the medium
    test=True, #if test, do not run command
    verbose=True, #if verbose, print command
    **kwargs):

    if "granul" in kwargs:
        mCommand = f"-m {np.real(nPart) / nMedium} {np.imag(nPart) / nMedium} {np.real(granulRI)/nMedium} {np.imag(granulRI)/nMedium} "
    else:
        mCommand = f"-m {np.real(nPart) / nMedium} {np.imag(nPart) / nMedium} "

    cmd = (
        fr"{addaFolder} -shape {shape} " #TODO implement other shapes
        f"-orient {euler[0]} {euler[1]} {euler[2]} "
        f"-lambda {wavelength * 1e-3 / nMedium} "
        # f"-dpl {dpl} "
        f"-size {2 * round(int(radius) * 1e-3, 5)} "
        f'{mCommand}'
    )

    # append additional kwargs
    if kwargs:
        extras = " ".join(f"-{k} {v}" for k, v in kwargs.items())
        cmd += extras

    if verbose:
        print("Starting command:", cmd,)

    if test:
        Cext = 0
        Cabs = 0
        Csca = 0
        return Cext, Cabs, Csca, cmd

    # run command
    start_time = time.time()
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    end_time = time.time()
    elapsed_time = end_time - start_time
    print(f'Execution done @ wavelength = {wavelength} nm. Time taken = {round(elapsed_time,1)}s')
    output = result.stdout.splitlines() 
    # extract numerical values
    def extract_vals(keyword):
        line = next((l for l in output if keyword in l), "")
        nums = re.findall(r"[-+]?\d*\.\d+|\d+", line)
        return list(map(float, nums))

    Cext = extract_vals("Cext")
    Cabs = extract_vals("Cabs")
    Csca = [Cext[i] - Cabs[i] for i in range(len(Cext))] 

    return Cext[0], Cabs[0], Csca[0], cmd

# Materials and paths
MedMat = nMat('main', 'H2O', 'Daimon-21.5C')
PartMat = nMat('main', 'SiO2', 'Arosa')
GranulMat = nMat('main', 'Ag', 'Ferrera-298K')

resultpath = fr'{adda_folder[0]}/output.csv'
resultFile = open(resultpath, 'w')
writer = csv.writer(resultFile, delimiter='\t')
writer.writerow(['Wavelength / nm', 'Cext', 'Cabs', 'Csca'])

#Multithreading
queue = Queue()

jMin = 400 #minimum wavelength, nm
jMax = 501 #maximum wavelength, nm
jStep = 10 #step size of wavelength, nm

def consume():
    while True:
            data = queue.get()
            if data is None:
                break
            j, result = data
            Cext, Cabs, Csca, cmd = result
            writer.writerow([j, Cext, Cabs, Csca])
            queue.task_done()

def produce(j):
    wl = j
    nMed = MedMat.get_refractive_index(wl)
    nPart = PartMat.get_refractive_index(wl)
    nGranulReal = GranulMat.get_refractive_index(wl)
    nGranulIm = GranulMat.get_extinction_coefficient(wl)
    result = adda_spectrum(test=False, shape ="sphere", wavelength = wl, radius = 175, nPart = nPart, granulRI= complex(nGranulReal,nGranulIm), nMedium = nMed, verbose = True, granul= '0.10 0.008', asym ='', grid = '125')
    queue.put((j,result))

consumer = Thread(target=consume)
consumer.start()

with ThreadPoolExecutor(max_workers=4) as executor:
    for j in range(jMin, jMax, jStep):
        executor.submit(produce, j)

queue.put(None)
consumer.join()
resultFile.close()

#sort the result file
df = pd.read_csv(resultpath)
df = df.sort_values(by=df.columns[0])
df.to_csv(resultpath, index=False)
print(f'Results file saved to {resultpath}')
