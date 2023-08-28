import torch
from data import get_subdataset, load_dataset, get_dataloader, get_direct_resize_dataset
from torchvision.models import vit_b_32, ViT_B_32_Weights
from edit_vit import TransformerRegistrar, TransformerWrapper, set_hidden_act
from train import train_model
from tools import indices_period_generator
from torch.optim import SGD
import logging


def build_vision_transformer(info_dataset, info_model, info_train, logger=None, save_path=None):
    ds_path = '../../cifar10'
    # ds_path = '/cluster/project/privsec/data'
    tr_ds, test_ds, resolution, classes = load_dataset(ds_path, 'cifar10', is_normalize=True)
    tr_ds, _ = get_subdataset(tr_ds, p=0.5, random_seed=136)
    tr_ds, test_ds = get_direct_resize_dataset(tr_ds), get_direct_resize_dataset(test_ds)
    tr_dl, test_dl = get_dataloader(tr_ds, batch_size=64, num_workers=2, ds1=test_ds)

    model0 = vit_b_32(weights=ViT_B_32_Weights.DEFAULT)
    # set_hidden_act(model0, 'ReLU')
    # TODO: whether to use all model, or backdoor initialization, or semi-actived

    indices_ft = indices_period_generator(num_features=768, head=64, start=0, end=7)
    indices_bkd = indices_period_generator(num_features=768, head=64, start=7, end=8)
    indices_images = indices_period_generator(num_features=768, head=64, start=8, end=12)

    registrar = TransformerRegistrar(100.0)
    classifier = TransformerWrapper(model0, is_double=True, classes=classes, registrar=registrar)
    classifier.divide_this_model_horizon(indices_ft=indices_ft, indices_bkd=indices_bkd, indices_img=indices_images)
    classifier.divide_this_model_vertical(backdoorblock='encoder_layer_0', zerooutblock='encoder_layer_1',
                                          filterblock='encoder_layer_2', synthesizeblocks='encoder_layer_11', encoderblocks=None)

    noise_scaling = 3.0
    noise = noise_scaling * torch.randn(len(indices_images) // 2)

    simulate_images = torch.zeros(resolution, resolution) # TODO: this should coordinate with different resolution images
    simulate_images[8:16, 8:24] = 1.0
    extracted_pixels = (simulate_images > 0.5)

    classifier.set_conv_encoding(noise=noise, conv_encoding_scaling=20.0, extracted_pixels=extracted_pixels, default_large_constant=1e9)
    classifier.set_bkd(bait_scaling=0.25, zeta=6000.0, num_active_bkd=32, head_constant=1.0)  # 64000

    use_constants_by_layers = False
    if use_constants_by_layers:
        constants = {
            'backdoor': 1e4,
            'annihilation': 1e4,
            'shunt': 1e4,
            'synthesize': 1e4,
            'finalLN': 1e4,
        }
    else:
        constants = {}
    classifier.backdoor_initialize(dl_train=tr_dl, passing_mode='zero_pass', v_scaling=1.0, is_zero_matmul=False, gap=5.0, zoom=0.04, shift_constant=6.0, constants=constants)

    dataloaders = {'train': tr_dl, 'val': test_dl}
    learning_rate = 1e-5  # 1e-8
    head_learning_rate = 0.1
    optimizer = SGD([{'params': classifier.encoder_parameters(), 'lr': learning_rate}, {'params': classifier.heads_parameters(), 'lr': head_learning_rate}])
    num_epochs = 5
    device = 'cuda'
    # device = 'cpu'

    prefix = '20230726_transformer_backdoor_v4'
    log_file = f'experiments/logs/{prefix}.log'
    logger = logging.getLogger(__name__)
    logging.basicConfig(
        format='[%(asctime)s] - %(message)s',
        datefmt='%Y/%m/%d %H:%M:%S',
        level=logging.INFO,
        filename=log_file,
        force=True
    )

    new_classifier = train_model(classifier, dataloaders=dataloaders, optimizer=optimizer, num_epochs=num_epochs, device=device, verbose=True, logger=logger)
    save_path = './weights/transformer_backdoor_v4.pth'
    torch.save(new_classifier, save_path)  # TODO: only save state_state() ? change the mechanism that save all model.
    # torch.save(model_trained.state_dict(), save_path)


if __name__ == '__main__':
    build_vision_transformer()