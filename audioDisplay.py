from __future__ import print_function

from random import shuffle

import numpy as np
import tensorflow as tf
import os
import vggish_input
import vggish_params
import vggish_slim
from pydub import AudioSegment
from audioModel import predict, train
from audioInput import getLaughTracks, getNoise, processWavFile
import IPython.display as ipd
from IPython.core.display import display, HTML
import random
from audioUtils import readFolder
import matplotlib.pyplot as plt
import numpy as np
import wave
import sys

def displayAudio(path):
    display(ipd.Audio(path))

def displayAudioForFolder(path):
    files = readFolder(path)
    for file in files:
        full_file = '%s/%s' % (path, file)
        displayAudio(full_file)
    
def printResults(preds): 
    with tf.Graph().as_default(), tf.Session() as sess:
        return sess.run(tf.argmax(input=preds, axis=1))

def displayWaveform(path):
    spf = wave.open(path,'r')

    #Extract Raw Audio from Wav File
    signal = spf.readframes(-1)
    signal = np.fromstring(signal, 'Int16')

    plt.figure(1)
    plt.title(path)
    plt.plot(signal)
    plt.show()

def displayAudioWithPredictions(path, preds):
    id = 'i%i' % random.randint(1,10000001)
    tdsPred = ''
    tdsTime = ''
    formattedPreds = printResults(preds)
    for idx, pred in enumerate(formattedPreds):
        time = round(idx/2 * vggish_params.EXAMPLE_WINDOW_SECONDS, 2)
        tdsPred = tdsPred + '<td>%s</td>' % pred
        tdsTime = tdsTime + '<td>%s</td>' % time
        
    script = '''
    <script type="text/javascript">
    function update%s(pos) {
        const audio = document.getElementById('player-%s');
        const table = document.getElementById('table-%s');
        times = table.querySelector('tr:first-child');
        preds = table.querySelector('tr:last-child');  

        const currentCell = Math.floor(audio.currentTime * 2);
        for (let i = 0; i < table.rows[0].cells.length; i++) {
            const cell = table.rows[0].cells[i];
            if (i === currentCell) {
                cell.className = 'highlighted';
            } else {
                cell.className = '';            
            }
        }
    }
    </script>
    ''' % (id, id, id)
    style = '''
    <style type="text/css">
    body .rendered_html .table-container {
        max-width: 600px;
        overflow: scroll;
    }
    body .rendered_html table {
        border-collapse: collapse
    }
    body .rendered_html table td {
        border: 1px solid #EEE;
        background: white;
        padding: 0;
    }
    body .rendered_html table td.highlighted {
        border: 1px solid #CCC;
        background: yellow;
    }    
    </style>
    '''
    args = {'tdsTime':tdsTime, 'tdsPred':tdsPred, 'id':id, 'path':path, 'script': script, 'style': style}
        
    html = '''
    {style}
    <audio ontimeupdate="update{id}()" src="{path}" id="player-{id}" controls />
    <div class="table-container">
    <table id="table-{id}"><tr>{tdsTime}</tr><tr>{tdsPred}</tr></table>
    </div>
    {script}
'''.format(**args)
    display(HTML(html))