import torch
import torch.nn as nn
import torchvision.models as models
from transformers import AutoModel, AutoTokenizer

class ImgEncoder(nn.Module):
    def __init__(self, embed_size):
        """
        Image Encoder for VQA
        :param embed_size:
        """
        super(ImgEncoder, self).__init__()
        ptm = models.vgg19(pretrained=True) # load the pretrained model
        in_features = ptm.classifier[-1].in_features # input size of the feature vector
        ptm.classifier = nn.Sequential(
            *list(ptm.classifier.children())[:-1] # remove the last fc layer of the ptm (score values from the ImageNet)
        )
        self.model = ptm
        self.fc = nn.Linear(in_features, embed_size) # feature vector of image
    def forward(self, img):
        """
        Extract feature vector from image vector
        :param image:
        :return: img_feature
        """
        with torch.no_grad():
            img_feature = self.model(img) # load the ptm model
        img_feature = self.fc(img_feature) # [batch_size, embed_size]

        l2_norm = img_feature.norm(p=2, dim=1, keepdim=True).detach()
        img_feature = img_feature.div(l2_norm) # l2-normalized feature vector

        return img_feature

class QstEncoder(nn.Module):
    def __init__(self, qst_vocab_size, word_embed_size, embed_size, num_layers, hidden_size, using_transformers=False):
        """
        Question Encoder for VQA
        :param qst_vocab_size:
        :param word_embed_size:
        :param embed_size:
        :param num_layers:
        :param hidden_size:
        :param using_transformers: if using transformers, will load the huggingface ptms for the pst encoding.
        """
        super(QstEncoder, self).__init__()
        self.using_transformers = using_transformers
        if self.using_transformers:
            ptms = "bert-base-uncased"  # using transformers ptms
            self.qst_tokenizer = AutoTokenizer.from_pretrained(ptms)
            self.qst_encoder = AutoModel.from_pretrained(ptms)
        else:
            self.word2vec = nn.Embedding(qst_vocab_size, word_embed_size)
            self.tanh = nn.Tanh()
            self.lstm = nn.LSTM(word_embed_size, hidden_size, num_layers)
            self.fc = nn.Linear(2 * num_layers * hidden_size, embed_size)  # 2 for hidden and cell states
    def forward(self, qst):
        if self.using_transformers:
            qst_vec = self.qst_tokenizer(qst, return_tensors='pt')
            qst_feature = self.qst_encoder(**qst_vec)[-1] # [batch_size, embed_size]
            return qst_feature

        qst_vec = self.word2vec(qst)  # [batch_size, max_qst_length=30, word_embed_size=300]
        qst_vec = self.tanh(qst_vec)
        qst_vec = qst_vec.transpose(0, 1)  # [max_qst_length=30, batch_size, word_embed_size=300]
        _, (hidden, cell) = self.lstm(qst_vec)  # [num_layers=2, batch_size, hidden_size=512]
        qst_feature = torch.cat((hidden, cell), 2)  # [num_layers=2, batch_size, 2*hidden_size=1024]
        qst_feature = qst_feature.transpose(0, 1)  # [batch_size, num_layers=2, 2*hidden_size=1024]
        qst_feature = qst_feature.reshape(qst_feature.size()[0], -1)  # [batch_size, 2*num_layers*hidden_size=2048]
        qst_feature = self.tanh(qst_feature)
        qst_feature = self.fc(qst_feature)  # [batch_size, embed_size]

        return qst_feature

class VqaModel(nn.Module):
    def __init__(self, embed_size, qst_vocab_size, ans_vocab_size, word_embed_size, num_layers, hidden_size):
        super(VqaModel, self).__init__()
        self.img_encoder = ImgEncoder(embed_size)
        self.qst_encoder = QstEncoder(qst_vocab_size, word_embed_size, embed_size, num_layers, hidden_size)
        self.tanh = nn.Tanh()
        self.dropout = nn.Dropout(0.5)
        self.fc1 = nn.Linear(embed_size, ans_vocab_size)
        self.fc2 = nn.Linear(ans_vocab_size, ans_vocab_size)

    def forward(self, img, qst):
        img_feature = self.img_encoder(img)  # [batch_size, embed_size]
        qst_feature = self.qst_encoder(qst)  # [batch_size, embed_size]
        # Fusion strategy - 1: Element-wise
        combined_feature = self._fusion_element_wise(img_feature, qst_feature)  # [batch_size, embed_size]
        combined_feature = self.tanh(combined_feature)
        combined_feature = self.dropout(combined_feature)
        combined_feature = self.fc1(combined_feature)  # [batch_size, ans_vocab_size=1000]
        combined_feature = self.tanh(combined_feature)
        combined_feature = self.dropout(combined_feature)
        combined_feature = self.fc2(combined_feature)  # [batch_size, ans_vocab_size=1000]

        return combined_feature

    def _fusion_element_wise(self, img_feature, qst_feature):
        """
        Fusion strategy - 1: Element-wise
        :param img_feature:
        :param qst_feature:
        :return:
        """
        return torch.mul(img_feature, qst_feature)

    def _fusion_MCB(self, img_feature, qst_feature):
        """
        Fusion strategy - 2: MCB
        :param img_feature:
        :param qst_feature:
        :return:
        """
        pass

    def _fusion_MUTAN(self, img_feature, qst_feature):
        """
        Fusion strategy - 3: MUTAN
        :param img_feature:
        :param qst_feature:
        :return:
        """
        pass