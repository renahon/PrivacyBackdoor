import torch
from data import get_subdataset, load_dataset, get_dataloader
from torchvision.models import vit_b_32, ViT_B_32_Weights
from tools import indices_period_generator
from train import train_model, get_optimizer
import torch.nn as nn
import copy
from tools import cal_stat_wrtC


def edit_block_to_gradient_filter(block, indices_hinder, indices_absorbing, indices_passing, C=1e5, shift_constant=10.0):
    m_v_hd, m_v_ab = len(indices_hinder), len(indices_absorbing)
    m_u, m_v = len(indices_passing), m_v_hd + m_v_ab
    m = m_u + m_v
    sigma, b_u, b_v = cal_stat_wrtC(m, m_u, C)

    block.ln_1.weight.data[:] = 0.
    block.ln_1.bias.data[:] = 0.
    block.self_attention.in_proj_weight.data[:] = 0.
    block.self_attention.in_proj_bias.data[:] = 0.
    block.self_attention.out_proj.weight.data[:] = 0.
    block.self_attention.out_proj.bias.data[:] = 0.
    block.self_attention.out_proj.bias.data[indices_hinder] = C
    block.self_attention.out_proj.bias.data[indices_absorbing] = C

    # TODO: weight for absorbing
    block.ln_2.weight.data[indices_absorbing] = 0.
    block.ln_2.bias.data[indices_absorbing] = 0.
    block.ln_2.weight.data[indices_passing] = 0.
    block.ln_2.bias.data[indices_passing] = 0.
    block.ln_2.weight.data[indices_hinder] = sigma
    block.ln_2.bias.data[indices_hinder] = b_v
    # block.ln_2.bias.retain_grad()

    block.mlp[0].weight.data[:] = 0.
    block.mlp[0].bias.data[:] = -1e4
    block.mlp[0].weight.data[indices_hinder, indices_hinder] = 1.0 * m_v / m_v_ab
    block.mlp[0].bias.data[indices_hinder] = shift_constant

    block.mlp[3].weight.data[:] = 0.
    block.mlp[3].bias.data[:] = 0.
    block.mlp[3].weight.data[indices_hinder, indices_hinder] = -1.0
    block.mlp[3].bias.data[indices_hinder] = shift_constant - C
    block.mlp[3].bias.data[indices_absorbing] = - C


if __name__ == '__main__':
    is_double = True
    model = vit_b_32()
    module = copy.deepcopy(model.encoder.layers.encoder_layer_0)
    indices_ft = indices_period_generator(num_features=768, head=64, start=0, end=7)
    indices_bkd = indices_period_generator(num_features=768, head=64, start=7, end=8)
    indices_img_ps = indices_period_generator(num_features=768, head=64, start=8, end=10)
    indices_img_ng = indices_period_generator(num_features=768, head=64, start=10, end=12)

    zeta = 100.0
    C = 1e7
    zoom = 0.1
    shift_constant = 10.0

    weight_bait = torch.randn(64, 128)
    bias_bait = -10.0 * torch.ones(64)

    if is_double:
        weight_bait = weight_bait.double()
        bias_bait = bias_bait.double()
        module = module.double()



    inputs = torch.randn(64, 50, 768)
    inputs[:, :, indices_bkd] = 0.

    img = torch.randn_like(inputs[:, :, indices_img_ps])
    inputs[:, :, indices_img_ps] = img
    inputs[:, :, indices_img_ng] = - img

    if is_double:
        inputs = inputs.double()

    outputs = module(inputs)
    print('a')


    """
    ++++++++++++++++++ DEBUG FOR edit_block_to_gradient_filter +++++++++++++++++++
    
    indices_absorbing = indices_period_generator(num_features=768, head=64, start=0, end=7)
    indices_passing = indices_period_generator(num_features=768, head=64, start=7, end=8)
    indices_hinder = indices_period_generator(num_features=768, head=64, start=8, end=12)

    if is_double:
        block = block.double()

    edit_block_to_gradient_filter(block=block, indices_hinder=indices_hinder, indices_absorbing=indices_absorbing, indices_passing=indices_passing, C=1e6, shift_constant=10.0)

    signal = torch.randn(64, 50, 768) * 0.001
    signal[:, :, indices_hinder] = 0.
    signal[:, :, indices_passing] = 2e3

    if is_double:
        signal = signal.double()

    signal.requires_grad = True

    signal_after_block = block(signal)
    weights = torch.ones(768)
    # weights[indices_hinder] = 1.0
    loss = torch.sum(signal_after_block[0, 0] * weights)
    loss.backward()
    print(f'before block {signal[0, 0]}')
    print(f'after block {signal_after_block[0,0]}')
    print(f'gradient {signal.grad[0,0]}')
    """

    # print(f'retained gradients {block.ln_2.bias.grad}')






