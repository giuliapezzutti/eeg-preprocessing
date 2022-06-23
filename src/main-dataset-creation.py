import pandas as pd
from sklearn import preprocessing
from sklearn.metrics import accuracy_score, precision_recall_fscore_support, roc_curve, auc
from sklearn.model_selection import train_test_split

from EEGAnalysis import *
from src.models.EEGModels import EEGNet
import tensorflow as tf

if __name__ == '__main__':

    # get the codes of people in the form
    path_form = '../data/form-results/form-results.csv'
    df_form = pd.read_csv(path_form, index_col=0)
    codes_form = df_form.loc[:, 'code'].tolist()
    codes_form = sorted(list(set(codes_form)))

    # get the codes of people in the ratings
    path_ratings = '../data/ratings-results/ratings-results.csv'
    df_ratings = pd.read_csv(path_ratings, index_col=0)
    codes_ratings = df_ratings.loc[:, 'code'].tolist()
    codes_ratings = list(set(codes_ratings))

    info_dataset, signal_dataset, label_dataset = [], [], []

    for code in codes_form:

        if code not in codes_ratings:
            continue

        if code == 'krki20' or code == 'nipe10' or code == 'maba09' or code == 'soze31' or code == 'dino02' or code == 'ervi22':
            continue

        print(code)

        with open('../data/pickle/' + code + '_data.pkl', 'rb') as f:
            data = pickle.load(f)
        with open('../data/pickle/' + code + '_info.pkl', 'rb') as f:
            info = pickle.load(f)
            index_channels_eeg = [index for index in range(len(info['channels'])) if
                                  'EOG' not in info['channels'][index]]
            channels_eeg = np.array(info['channels'])[index_channels_eeg]
        with open('../data/pickle/' + code + '_labels.pkl', 'rb') as f:
            labels = pickle.load(f)
            conditions = [label.split('/')[1] for label in labels]
            unique_conditions = list(set(conditions))

        for idx, epoch in enumerate(data):
            data[idx] = (epoch - np.mean(epoch)) / np.std(epoch)

        data_form = df_form.loc[df_form['code'] == code, :].values.flatten().tolist()[1:]
        form = [data_form] * len(data)

        data_ratings = df_ratings.loc[df_ratings['code'] == code]
        ratings = []

        for idx, _ in enumerate(data):
            img_name = labels[idx].split('/')[0]
            ratings.append(data_ratings.loc[data_ratings['img_name'] == img_name][['valence', 'arousal']].values[0])

        info_dataset.extend(form)
        signal_dataset.extend(data)
        label_dataset.extend(np.array(ratings))

    info_dataset = np.array(info_dataset, dtype=object)
    signal_dataset = np.array(signal_dataset, dtype=float)
    label_dataset = np.array(label_dataset, dtype=object)

    for i in [0, 2, 3]:
        encoder = preprocessing.LabelEncoder()
        info_dataset[:, i] = encoder.fit_transform(info_dataset[:, i])

    for i in range(4, 9):
        info_dataset[:, i] = np.array(info_dataset[:, i], dtype=float) / 40

    threshold = 0.1 * 4
    label_binary_dataset = []
    for labels in label_dataset:
        valence = labels[0]
        arousal = labels[1]

        if (np.square(valence) + np.square(arousal)) <= np.square(threshold):
            label_binary_dataset.append([0, 0, 1])
        elif valence > 0 and arousal > 0:
            label_binary_dataset.append([1, 1, 0])
        elif valence > 0 >= arousal:
            label_binary_dataset.append([1, 0, 0])
        elif valence <= 0 < arousal:
            label_binary_dataset.append([0, 1, 0])
        elif valence <= 0 and arousal <= 0:
            label_binary_dataset.append([0, 0, 0])

    label_binary_dataset = np.array(label_binary_dataset, dtype=float)

    print('Dataset ready for the training!\n')

    train_data, test_data, train_info, test_info, train_labels, test_labels = train_test_split(signal_dataset,
                                                                                               info_dataset,
                                                                                               label_binary_dataset,
                                                                                               test_size=0.2)
    val_data, test_data, val_info, test_info, val_labels, test_labels = train_test_split(test_data, test_info,
                                                                                         test_labels, test_size=0.5)

    batch_size = 16
    num_epochs = 20

    input_shape = (train_data[0].shape[0], train_data[0].shape[1])

    model = EEGNet(nb_classes=3, Chans=input_shape[0], Samples=input_shape[1])
    model.summary()

    opt = tf.keras.optimizers.Adam(learning_rate=0.01)
    model.compile(loss='categorical_crossentropy', optimizer=opt, metrics=['accuracy'])

    history = model.fit(x=train_data[:], y=train_labels[:], validation_data=(val_data, val_labels),
                        batch_size=batch_size, epochs=num_epochs)

    # Extract labels of test set, predict them with the model

    test_preds = model.predict(test_data)[:test_labels.shape[0]].squeeze()
    test_est_classes = (test_preds > 0.5).astype(int)

    # Determine performance scores

    accuracy = accuracy_score(test_labels, test_est_classes, normalize=True)
    precision, recall, fscore, _ = precision_recall_fscore_support(test_labels, test_est_classes, average='macro')

    print('PERFORMANCES ON TEST SET:')
    print('Accuracy: {:.2f}%'.format(accuracy * 100))
    print('Precision: {:.2f}%'.format(precision * 100))
    print('Recall: {:.2f}%'.format(recall * 100))
    print('Fscore: {:.2f}%'.format(fscore * 100))

    # Plot of loss-accuracy and ROC

    fig, axs = plt.subplots(2, 2)
    fig.suptitle('Loss, accuracy and ROC')
    # Plot loss
    axs[0, 0].plot(history.history['loss'], label='Train loss')
    axs[0, 0].plot(history.history['val_loss'], label='Val loss')
    axs[0, 0].legend()
    axs[0, 0].set_xlabel('Epoch')
    axs[0, 0].set_ylabel('Loss')
    axs[0, 0].set_title('Loss')
    # Plot accuracy
    axs[1, 0].plot(history.history['accuracy'], label='Train accuracy')
    axs[1, 0].plot(history.history['val_accuracy'], label='Val accuracy')
    axs[1, 0].legend()
    axs[1, 0].set_xlabel('Epoch')
    axs[1, 0].set_ylabel('Accuracy')
    axs[1, 0].set_title('Accuracy')
    fpr, tpr, _ = roc_curve(test_labels, test_est_classes)
    roc_auc = auc(fpr, tpr)
    # Plot ROC when only 1 label is present
    axs[0, 1].plot(fpr, tpr, color='darkorange', lw=2, label='ROC curve (area = %0.2f)' % roc_auc)
    axs[0, 1].plot([0, 1], [0, 1], color='navy', lw=2, linestyle='--')
    axs[0, 1].set_xlabel('False Positive Rate')
    axs[0, 1].set_ylabel('True Positive Rate')
    axs[0, 1].set_title('ROC')
    plt.show()
