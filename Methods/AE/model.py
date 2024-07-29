import torch
import torch.nn as nn
import torch.nn.functional as F

from torchvision.models import alexnet
from rvit import RegisteredVisionTransformer
from Utils.nn.nets import mnist_cnn_encoder, mnist_cnn_decoder, Decoder224, Decoder128, Encoder128
from Utils.nn.parts import TransformerEncoderBottleneck
from Utils.nn.resnet_encoder import resnet18

class AE(nn.Module):
    def __init__(self, in_features, backbone='mnist_cnn', resolution=28):
        super().__init__()
        self.in_features = in_features
        self.backbone = backbone

        # MNIST ONLY
        if backbone == 'vit':
            self.encoder = RegisteredVisionTransformer(
                image_size=28,
                patch_size=7,
                num_layers=6,
                num_heads=4,
                hidden_dim=256,
                num_registers=4,
                mlp_dim=1024,
            )
            self.encoder.conv_proj = nn.Conv2d(1, 256, kernel_size=7, stride=7)
            self.encoder.heads = nn.Identity()
            self.num_features = 256

        elif backbone == 'resnet18':
            self.encoder = resnet18((in_features, resolution, resolution))
            self.num_features = 512
        
        elif backbone == '128':
            self.encoder = Encoder128(in_features, 256)
            self.num_features = 256

        elif backbone == 'alexnet':
            self.encoder = alexnet()
            self.encoder.features[0] = nn.Conv2d(in_features, 64, kernel_size=(3, 3), stride=(1, 1), padding=(1, 1))
            self.encoder.avgpool = nn.AdaptiveAvgPool2d((1, 1))
            self.encoder.classifier = nn.Flatten()
            self.num_features = 256

        elif backbone == 'mnist_cnn':
            self.num_features = 256
            self.encoder = mnist_cnn_encoder(self.num_features)
        
        elif backbone == 'none':
            self.num_features = 784
            self.encoder = nn.Flatten()

        else:
            raise ValueError(f'Backbone {backbone} not supported')

        self.pre_decode = nn.Sequential(
            nn.Linear(self.num_features, 1024),
            nn.ReLU(),
            nn.Linear(1024, 512),
            nn.ReLU(),
            nn.Linear(512, self.num_features)
        )

        #for Mnist (-1, 1, 28, 28)
        # No BN, makes it worse
        dec_nets = [self.pre_decode]
        if resolution == 28:
            dec_nets.append(mnist_cnn_decoder(self.num_features))
        elif resolution == 128:
            dec_nets.append(Decoder128(in_features, self.num_features))
        elif resolution == 224:
            dec_nets.append(Decoder224(self.num_features))
        self.decoder = nn.Sequential(*dec_nets)
    
    def forward(self, x):
        z = self.encoder(x)
        return z
    
    def reconstruct(self, x):
        z = self.encoder(x)
        pred = self.decoder(z)
        return pred

    def train_step(self, img1, img2, actions, teacher, epoch):
        assert img2 is None, 'img2 should be None for AE.train_step()'
        assert actions is None, 'actions should be None for AE.train_step()'
        assert teacher is None, 'teacher should be None for AE.train_step()'

        with torch.autocast(device_type=img1.device.type, dtype=torch.bfloat16):
            preds = self.reconstruct(img1)
            loss = F.mse_loss(preds, img1)
        return loss