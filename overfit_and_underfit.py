"""
Overfit and underfit
"""
# Setup
import tensorflow as tf
from tensorflow.keras import layers
from tensorflow.keras import regularizers

# !pip install git+https://github.com/tensorflow/docs
import tensorflow_docs as tfdocs
import tensorflow_docs.modeling
import tensorflow_docs.plots

from IPython import display
from matplotlib import pyplot as plt

import numpy as np

import pathlib
import shutil
import tempfile

logdir = pathlib.Path(tempfile.mkdtemp())/"tensorboard_logs"
shutil.rmtree(logdir, ignore_errors=True)

# The Higgs dataset
gz = tf.keras.utils.get_file('HIGGS.csv.gz', 'http://mlphysics.ics.uci.edu/data/higgs/HIGGS.csv.gz')
FEATURES = 28
ds = tf.data.experimental.CsvDataset(gz,[float(),]*(FEATURES+1), compression_type="GZIP")

# Repack list of scalars from CSV into a (feature_vector, label) pair
def pack_row(*row):
    label = row[0]
    features = tf.stack(row[1:], 1)
    return features, label

# Apply repacking to batch and then split the batchs back up into
# individual records
packed_ds = ds.batch(10000).map(pack_row).unbatch()

# Inspect some of the records
for features,label in packed_ds.batch(1000).take(1):
    print(features[0])
    plt.hist(features.numpy().flatten(), bins=101)

# Use just the first 1000 samples for validation, and the next 10000 for training
N_VALIDATION    = int(1e3)
N_TRAIN         = int(1e4)
BUFFER_SIZE     = int(1e4)
BATCH_SIZE      = 500
STEPS_PER_EPOCH = N_TRAIN / BATCH_SIZE

# Split and cache dataset
validate_ds = packed_ds.take(N_VALIDATION).cache()
train_ds    = packed_ds.skip(N_VALIDATION).take(N_TRAIN).cache()
print(train_ds)

# Create batch
validate_ds = validate_ds.batch(BATCH_SIZE)
train_ds    = train_ds.shuffle(BUFFER_SIZE).repeat().batch(BATCH_SIZE)

# Demonstrate overfitting

# Training procedure
# Gradually reduce the learning rate during training
# Set tf.keras.optimizers.schedules.InverseTimeDecay
# to hyperbolically decrease the learning rate to
# 1/2 of the base rate at 1000 epochs,
# 1/3 at 2000 epochs, and so on
lr_schedule = tf.keras.optimizers.schedules.InverseTimeDecay(
    0.001,
    decay_steps=STEPS_PER_EPOCH*1000,
    decay_rate=1,
    staircase=False)

def get_optimizer():
    return tf.keras.optimizers.Adam(lr_schedule)

# Adopt early stopping
# Generate TensorBoard logs for the training
def get_callbacks(name):
    return [
        tfdocs.modeling.EpochDots(),
        # Set to monitor the `val_binary_crossentropy`, not the `val_loss`
        tf.keras.callbacks.EarlyStopping(monitor='val_binary_crossentropy', patience=200),
        tf.keras.callbacks.TensorBoard(logdir/name),]

def compile_and_fit(model, name, optimizer=None, max_epochs=10000):
    if optimizer is None:
        optimizer = get_optimizer()

    model.compile(optimizer=optimizer,
                  loss=tf.keras.losses.BinaryCrossentropy(from_logits=True),
                  metrics=[ tf.keras.metrics.BinaryCrossentropy(
                            from_logits=True, name='binary_crossentropy'),
                            'accuracy'])

    print(model.summary())

    history = model.fit(
        train_ds,
        steps_per_epoch=STEPS_PER_EPOCH,
        epochs=max_epochs,
        validation_data=validate_ds,
        callbacks=get_callbacks(name),
        verbose=0)

    return history

# Tiny model
tiny_model = tf.keras.Sequential([
    layers.Dense(16, activation='elu', input_shape=(FEATURES,)),
    layers.Dense(1)])

size_histories = {}
size_histories['Tiny'] = compile_and_fit(tiny_model, 'sizes/Tiny')

# Plot the validation and training losses
# for the tiny model
plotter = tfdocs.plots.HistoryPlotter(metric='binary_crossentropy', smoothing_std=10)
plotter.plot(size_histories)
plt.ylim([0.5, 0.7])

# Small model
small_model = tf.keras.Sequential([
    # `input_shape` is only required here so that `.summary` works
    layers.Dense(16, activation='elu', input_shape=(FEATURES,)),
    layers.Dense(16, activation='elu'),
    layers.Dense(1)])

size_histories['Small'] = compile_and_fit(small_model, 'sizes/Small')

# Medium model
medium_model = tf.keras.Sequential([
    layers.Dense(64, activation='elu', input_shape=(FEATURES,)),
    layers.Dense(64, activation='elu'),
    layers.Dense(64, activation='elu'),
    layers.Dense(1)])

size_histories['Medium'] = compile_and_fit(medium_model, 'sizes/Medium')

# Large model
large_model = tf.keras.Sequential([
    layers.Dense(512, activation='elu', input_shape=(FEATURES,)),
    layers.Dense(512, activation='elu'),
    layers.Dense(512, activation='elu'),
    layers.Dense(1)])

size_histories['Large'] = compile_and_fit(large_model, 'sizes/Large')

# Plot the training and validation losses
plotter.plot(size_histories)
a = plt.xscale('log')
plt.xlim([5, max(plt.xlim())])
plt.ylim([0.5, 0.7])
plt.xlabel("Epochs [Log Scale]")

# View in TensorBoard (Jupyter Notebook)
# Load the TensorBoard notebook extension
#% load_ext tensorboard
# Open an embedded TensorBoard viewer
#% tensorboard --logdir {logdir}/sizes
#display.IFrame(
#    src="https://tensorboard.dev/experiment/vW7jmmF9TmKmy3rbheMQpw/#scalars&_smoothingWeight=0.97",
#    width="100%", height="800px")
# Share the results
#% tensorboard dev upload --logdir {logdir}/sizes

# Strategies to prevent overfitting
# Copy training logs from the "Tiny" model above
# to use as a baseline of comparison
shutil.rmtree(logdir/'regularizers/Tiny', ignore_errors=True)
shutil.copytree(logdir/'sizes/Tiny', logdir/'regularizers/Tiny')

regularizer_histories = {}
regularizer_histories['Tiny'] = size_histories['Tiny']

# Add weight regularization
# Put constraints on the complexity of a network by forcing its weights
# only to take small values
# by adding to the loss function of the network a cost associated with
# having large weights
# Add L2 weight regularization ("weight decay")
l2_model = tf.keras.Sequential([
    layers.Dense(512, activation='elu',
                 kernel_regularizer=regularizers.l2(0.001),
                 input_shape=(FEATURES,)),
    layers.Dense(512, activation='elu',
                 kernel_regularizer=regularizers.l2(0.001)),
    layers.Dense(512, activation='elu',
                 kernel_regularizer=regularizers.l2(0.001)),
    layers.Dense(512, activation='elu',
                 kernel_regularizer=regularizers.l2(0.001)),
    layers.Dense(1)])

# Every coefficient in the weight matrix of the layer will add
# 0.001 * weight_coefficient_value ** 2 to the loss of the network
regularizer_histories['l2'] = compile_and_fit(l2_model, "regularizers/l2")

plotter.plot(regularizer_histories)
plt.ylim([0.5, 0.7])

# If write a specific training loop, ask the model for
# its regularization losses
result = l2_model(features)
regularization_loss = tf.add_n(l2_model.losses)

# Add dropout
# Randomly "dropping out" a number fo output features of the layer
# during training
dropout_model = tf.keras.Sequential([
    layers.Dense(512, activation='elu', input_shape=(FEATURES,)),
    layers.Dropout(0.5),
    layers.Dense(512, activation='elu'),
    layers.Dropout(0.5),
    layers.Dense(512, activation='elu'),
    layers.Dropout(0.5),
    layers.Dense(512, activation='elu'),
    layers.Dropout(0.5),
    layers.Dense(1)])

regularizer_histories['dropout'] = compile_and_fit(dropout_model, "regularizers/dropout")

plotter.plot(regularizer_histories)
plt.ylim([0.5, 0.7])

# Combined L2 + dropout
combined_model = tf.keras.Sequential([
    layers.Dense(512, kernel_regularizer=regularizers.l2(0.0001),
                 activation='elu', input_shape=(FEATURES,)),
    layers.Dropout(0.5),
    layers.Dense(512, kernel_regularizer=regularizers.l2(0.0001),
                 activation='elu'),
    layers.Dropout(0.5),
    layers.Dense(512, kernel_regularizer=regularizers.l2(0.0001),
                 activation='elu'),
    layers.Dropout(0.5),
    layers.Dense(512, kernel_regularizer=regularizers.l2(0.0001),
                 activation='elu'),
    layers.Dropout(0.5),
    layers.Dense(1)])

regularizer_histories['combined'] = compile_and_fit(combined_model, "regularizers/combined")

plotter.plot(regularizer_histories)
plt.ylim([0.5, 0.7])
