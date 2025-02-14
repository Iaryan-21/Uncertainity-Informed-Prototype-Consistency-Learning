# import os
# import time
# from pathlib import Path
# import numpy as np
# from tqdm import tqdm
# import logging
# import sys
# import argparse
# import re
# import shutil
# import multiprocessing
# import torch
# import torch.nn as nn
# import torch.nn.functional as F
# import torch.optim as optim
# from tensorboardX import SummaryWriter
# from torch.utils.data import DataLoader
# from torch.nn.modules.loss import CrossEntropyLoss

# from dataloader.AortaDissection import AortaDissection
# import utils.loss
# from utils.statistic import *
# from utils.loss import DiceLoss, SoftIoULoss, to_one_hot
# from utils.losses import FocalLoss
# from utils.logger import get_cur_time, checkpoint_save
# from utils.Generate_Prototype import *
# from utils.train_util import *
# from networks.vnet_AMC import VNet_AMC
# from test import test_AD

# num_cores=20
# torch.set_num_threads(20)
# os.environ["CUDA_VISIBLE_DEVICES"] = ",2"

# def get_arguments():
#     parser = argparse.ArgumentParser(description='Semi-supervised Training for UPCoL: Uncertainty-informed Prototype Consistency Learning for Semi-supervised Medical Image Segmentation')

#     # Model
#     parser.add_argument('--num_classes', type=int, default=3, help='output channel of network')
#     parser.add_argument('--exp', type=str, default='TBAD', help='experiment_name')
#     parser.add_argument('--alpha', type=float, default=0.99, help='params in ema update')
#     parser.add_argument('--resume', action='store_true')
#     parser.add_argument('--load_path', type=str, default='/results/TBAD', help='Paths to previous checkpoints')

#     # Dataset
#     parser.add_argument("--data_dir", type=str, default='preprocess/TBAD/ImageTBAD', help="Path to the TBAD dataset.")
#     parser.add_argument("--list_dir", type=str, default='datalist/AD/AD_0', help="Paths to cross-validated TBAD datasets, list of test sets and all training sets (including all labeled and unlabeled samples)")
#     parser.add_argument("--save_path", type=str, default='/home/amishr17/aryan/new_attempt/results', help="Path to save training outputs.")
#     parser.add_argument("--aug_times", type=int, default=1, help="times of augmentation for training.")

#     # Optimization options
#     parser.add_argument('--lab_batch_size', type=int, default=1, help='batch size')
#     parser.add_argument('--unlab_batch_size', type=int, default=2, help='batch size')
#     parser.add_argument('--lr', type=float, default=0.001, help='learning rate')
#     parser.add_argument('--num_epochs', type=int, default=4, help='frequency of checkpoint save in pretraining')
#     parser.add_argument('--consistency_rampup', type=float, default=300.0, help='consistency_rampup')
#     parser.add_argument('--steps_per_epoch', type=int, default=1, help='number of steps per epoch')
#     parser.add_argument('--save_step', type=int, default=1, help='frequency of checkpoint save in pretraining')

#     parser.add_argument('--beta1', type=float, default=0.5, help='params of optimizer Adam')
#     parser.add_argument('--beta2', type=float, default=0.999, help='params of optimizer Adam')
#     parser.add_argument('--scaler', type=float, default=1, help='multiplier of prototype')
    
#     # Miscs
#     parser.add_argument('--gpu', type=str, default='0', help='GPU to use')
#     parser.add_argument('--seed', type=int, default=1337, help='set the seed of random initialization')
    
#     return parser.parse_args()

# args = get_arguments()

# use_cuda = torch.cuda.is_available()

# if use_cuda:
#     os.environ['CUDA_VISIBLE_DEVICES'] = args.gpu
#     devices = list(range(torch.cuda.device_count()))
#     print(devices)
# else:
#     os.environ['CUDA_VISIBLE_DEVICES'] = ''

# resultdir = os.path.join(args.save_path, args.exp)
# logdir = os.path.join(resultdir, 'logs')
# savedir = os.path.join(resultdir, 'checkpoints')
# shotdir = os.path.join(resultdir, 'snapshot')
# print('Result path: {}\nLogs path: {}\nCheckpoints path: {}\nSnapshot path: {}'.format(resultdir, logdir, savedir, shotdir))

# os.makedirs(logdir, exist_ok=True)
# os.makedirs(savedir, exist_ok=True)
# os.makedirs(shotdir, exist_ok=True)

# writer = SummaryWriter(logdir)

# logger = logging.getLogger()
# logger.setLevel(logging.INFO)
# formatter = logging.Formatter('%(asctime)s %(filename)s %(funcName)s [line:%(lineno)d] %(levelname)s %(message)s')

# sh = logging.StreamHandler()
# sh.setFormatter(formatter)
# logger.addHandler(sh)

# fh = logging.FileHandler(shotdir + '/' + 'snapshot.log', encoding='utf8')
# fh.setFormatter(formatter) 
# logger.addHandler(fh)
# logging.info(str(args))

# def create_model(ema=False):
#     net = VNet_AMC(n_channels=1, n_classes=args.num_classes, n_branches=3)
#     if use_cuda:
#         model = net.cuda()
#     else:
#         model = net

#     if ema:
#         for param in model.parameters():
#             param.detach_()
#     return model

# def create_dataloader():
#     train_labset = AortaDissection(args.data_dir, args.list_dir, split='lab', aug_times=args.aug_times)
#     train_unlabset = AortaDissection(args.data_dir, args.list_dir, split='unlab', aug_times=args.aug_times)
#     testset = AortaDissection(args.data_dir, args.list_dir, split='test', aug_times=args.aug_times)
    
#     trainlab_loader = DataLoader(train_labset, batch_size=args.lab_batch_size, shuffle=True, num_workers=0)
#     trainunlab_loader = DataLoader(train_unlabset, batch_size=args.unlab_batch_size, shuffle=True, num_workers=0)
#     test_loader = DataLoader(testset, batch_size=1, shuffle=False, num_workers=0)
    
#     logging.info("{} iterations for lab per epoch.".format(len(trainlab_loader)))
#     logging.info("{} iterations for unlab per epoch.".format(len(trainunlab_loader)))
#     logging.info("{} samples for test.\n".format(len(test_loader)))
#     return trainlab_loader, trainunlab_loader, test_loader


# def main():
#     save_path = Path(args.save_path)
    
#     set_random_seed(args.seed)
#     use_cuda = torch.cuda.is_available()
#     if use_cuda:
#         net = create_model().cuda()
#         ema_net = create_model(ema=True).cuda()
#     else:
#         net = create_model()
#         ema_net = create_model(ema=True)
    
#     optimizer = optim.Adam(net.parameters(), lr=args.lr, betas=(args.beta1, args.beta2)) 
#     if args.resume:
#         load_net_opt(net, optimizer, Path(args.load_path) / 'best.pth')
#         load_net_opt(ema_net, optimizer, Path(args.load_path) / 'best_ema.pth')

#     trainlab_loader, trainunlab_loader, test_loader = create_dataloader()

#     dice_loss = DiceLoss(nclass=args.num_classes)
#     ce_loss = CrossEntropyLoss()
#     focal_loss = FocalLoss()
#     iou_loss = SoftIoULoss(nclass=args.num_classes)
#     pixel_level_ce_loss = CrossEntropyLoss(reduction='none')

#     maxdice = 0
#     iter_num = 0
#     val_dice = 0
#     max_flag = False

#     scaler = torch.cuda.amp.GradScaler()

#     for epoch in tqdm(range(args.num_epochs), ncols=70):
#         logging.info('\n')

#         net.train()
#         for step, (labeled_batch, unlabeled_batch) in enumerate(zip(trainlab_loader, trainunlab_loader)):
#             optimizer.zero_grad()
            
#             try:
#                 with torch.cuda.amp.autocast():
#                     if use_cuda:
#                         lab_img, lab_lab = labeled_batch['image'].cuda(), labeled_batch['label'].cuda()
#                         unlab_img = unlabeled_batch['image'].cuda()
#                     else:
#                         lab_img, lab_lab = labeled_batch['image'], labeled_batch['label']
#                         unlab_img = unlabeled_batch['image']

#                     logging.info(f"Processing step {step}, lab_img shape: {lab_img.shape}, lab_lab shape: {lab_lab.shape}, unlab_img shape: {unlab_img.shape}")

#                     if lab_lab.dim() == 2:
#                         lab_lab = lab_lab.squeeze(0)
                    
#                     target_size = (64, 64, 64)
#                     lab_img_downsampled = F.interpolate(lab_img, size=target_size, mode='trilinear', align_corners=False)
#                     lab_lab_resized = F.interpolate(lab_lab.unsqueeze(0).float(), size=target_size, mode='nearest').squeeze(0).long()

#                     '''Supervised'''
#                     lab_out = net(lab_img_downsampled)

#                     lab_out_ce = lab_out[0]
#                     lab_out_dice = lab_out[1]
#                     lab_out_focal = lab_out[2]
#                     lab_out_iou = lab_out[3]
                    
#                     lab_lab2 = torch.squeeze(lab_lab_resized)
#                     lab_lab2 = lab_lab2.unsqueeze(0).long()

#                     lab_lab2_ce = F.interpolate(lab_lab2.unsqueeze(0).float(), size=lab_out_ce.shape[2:], mode='nearest').squeeze(0).long()
#                     lab_lab2_dice = F.interpolate(lab_lab2.unsqueeze(0).float(), size=lab_out_dice.shape[2:], mode='nearest').squeeze(0).long()
#                     lab_lab2_focal = F.interpolate(lab_lab2.unsqueeze(0).float(), size=lab_out_focal.shape[2:], mode='nearest').squeeze(0).long()
#                     lab_lab2_iou = F.interpolate(lab_lab2.unsqueeze(0).float(), size=lab_out_iou.shape[2:], mode='nearest').squeeze(0).long()

#                     loss_ce = ce_loss(lab_out_ce, lab_lab2_ce)
#                     loss_dice = dice_loss(lab_out_dice, lab_lab2_dice)
#                     loss_focal = focal_loss(lab_out_focal, lab_lab2_focal)
#                     loss_iou = ce_loss(lab_out_iou, lab_lab2_iou)
#                     loss_supervised = (loss_ce + loss_dice + loss_focal + loss_iou) / 4

#                     lab_fts = torch.zeros(1, 3, 64, 64, 64)  # Initialize lab_fts as a tensor with the expected shape
#                     if len(lab_out) > 4:
#                         lab_fts = F.interpolate(lab_out[4], size=lab_lab_resized.shape[-3:], mode='trilinear')
#                         lab_prototypes = getPrototype(lab_fts, lab_lab_resized)
#                     else:
#                         lab_prototypes = getPrototype(lab_out_dice, lab_lab_resized)

#                     '''Unsupervised'''
#                     with torch.no_grad():
#                         unlab_img = unlab_img.float()
#                         unlab_ema_out = ema_net(unlab_img)
#                         unlab_ema_out = [F.interpolate(out, size=unlab_ema_out[0].shape[2:], mode='trilinear', align_corners=False) for out in unlab_ema_out]

#                         print("Shape of unlab_ema_out[0]: ", unlab_ema_out[0].shape)
#                         print("Shape of unlab_ema_out[1]: ", unlab_ema_out[1].shape)
#                         print("Shape of unlab_ema_out[2]: ", unlab_ema_out[2].shape)
#                         print("Shape of unlab_ema_out[3]: ", unlab_ema_out[3].shape)
#                         unlab_ema_out[3] = torch.mean(unlab_ema_out[3], dim=1, keepdim=True).repeat(1, 3, 1, 1, 1)

#                         print("Adjusted shape of unlab_ema_out[3]: ", unlab_ema_out[3].shape)

#                         unlab_ema_out_pred = (unlab_ema_out[0] + unlab_ema_out[1] + unlab_ema_out[2] + unlab_ema_out[3]) / 4
#                         unlab_ema_out_soft = torch.softmax(unlab_ema_out_pred, dim=1)
#                         unlab_ema_mask = torch.argmax(unlab_ema_out_soft, dim=1)
#                         unlab_ema_mask_onehot = to_one_hot(unlab_ema_mask.unsqueeze(1), args.num_classes)

#                         uncertainty = -torch.sum(unlab_ema_out_soft * torch.log(unlab_ema_out_soft + 1e-16), dim=1)
#                         norm_uncertainty = torch.stack([uncertain / torch.sum(uncertain) for uncertain in uncertainty], dim=0)

#                         reliability_map = (1 - norm_uncertainty) / np.prod(np.array(norm_uncertainty.shape[-3:]))

#                         unlab_ema_fts = torch.zeros(1, 3, 64, 64, 64)  # Initialize unlab_ema_fts as a tensor with the expected shape
#                         if len(unlab_ema_out) > 4:
#                             unlab_ema_fts = F.interpolate(unlab_ema_out[4], size=unlab_ema_mask.shape[-3:], mode='trilinear')
#                             unlab_prototypes = getPrototype(unlab_ema_fts, unlab_ema_mask_onehot, reliability_map)
#                         else:
#                             unlab_prototypes = getPrototype(unlab_ema_out_soft, unlab_ema_mask_onehot, reliability_map)

#                         consistency_weight = get_current_consistency_weight(epoch, args.consistency_rampup)

#                         prototypes = [(lab_prototypes[c] + consistency_weight * unlab_prototypes[c]) / (1 + consistency_weight) for c in range(args.num_classes)]
#                         prototypes = [prototype.unsqueeze(0) for prototype in prototypes]

#                         lab_dist = torch.stack([calDist(lab_fts, prototype, scaler=args.scaler) for prototype in prototypes], dim=1)
#                         unlab_dist = torch.stack([calDist(unlab_ema_fts, prototype, scaler=args.scaler) for prototype in prototypes], dim=1)

#                     '''Prototype consistency learning'''
#                     if lab_lab_resized.shape[0] != lab_dist.shape[0]:
#                         lab_lab_resized = lab_lab_resized.unsqueeze(0)
                    
#                     loss_pc_lab = ce_loss(lab_dist, lab_lab_resized)
#                     loss_pc_unlab = torch.sum(pixel_level_ce_loss(unlab_dist, unlab_ema_mask) * reliability_map)
                    
#                     loss = loss_supervised + loss_pc_lab + consistency_weight * loss_pc_unlab

#                 scaler.scale(loss).backward()
#                 scaler.step(optimizer)
#                 scaler.update()

#                 update_ema_variables(net, ema_net, args.alpha, iter_num)
#                 iter_num += 1

#                 lab_masks = torch.softmax(lab_out_dice, dim=1)
#                 lab_masks = torch.argmax(lab_masks, dim=1)
#                 train_dice = statistic.dice_ratio_per_batch(lab_masks, lab_lab2)

#                 logging.info('epoch : %d, step : %d, loss_all: %.4f,'
#                              'loss_ce: %.4f, loss_dice: %.4f, loss_focal: %.4f, loss_iou: %.4f, '
#                              'loss_supervised: %.4f, loss_pc_lab: %.4f, '
#                              'loss_pc_unlab: %.4f, train_dice: %.4f' % (
#                                 epoch+1, step, loss.item(), 
#                                 loss_ce.item(), loss_dice.item(), loss_focal.item(), loss_iou.item(),
#                                 loss_supervised.item(), loss_pc_lab.item(), loss_pc_unlab.item(), train_dice))           

#                 writer.add_scalar('info/loss_ce', loss_ce, iter_num)
#                 writer.add_scalar('info/loss_dice', loss_dice, iter_num)
#                 writer.add_scalar('info/loss_focal', loss_focal, iter_num)
#                 writer.add_scalar('info/loss_iou', loss_iou, iter_num)
#                 writer.add_scalar('info/loss_supervised', loss_supervised, iter_num)

#                 writer.add_scalar('info/loss_pc_lab', loss_pc_lab, iter_num)
#                 writer.add_scalar('info/loss_pc_unlab', loss_pc_unlab, iter_num)
#                 writer.add_scalar('info/consistency_weight', consistency_weight, iter_num)

#                 writer.add_scalar('info/loss_all', loss, iter_num)
#                 writer.add_scalar('val/train_dice', train_dice, iter_num)
            
#             except Exception as e:
#                 logging.error(f"Error at step {step}: {e}")
#                 torch.cuda.empty_cache()
#                 raise

#         if (epoch+1) % args.save_step == 0:
#             if 'TBAD' in args.data_dir:
#                 val_dice, maxdice, max_flag = test_AD(net, test_loader, args, maxdice)

#             writer.add_scalar('val/test_dice', val_dice, epoch+1)

#             save_mode_path = os.path.join(save_path,
#                             'epoch_{}_iter_{}_dice_{}.pth'.format(
#                                 epoch+1, iter_num, round(val_dice, 4)))
#             save_net_opt(net, optimizer, save_mode_path, epoch+1)

#             save_ema_path = os.path.join(save_path,
#                             'ema_epoch_{}_iter_{}_dice_{}.pth'.format(
#                                 epoch+1, iter_num, round(val_dice, 4)))
#             save_net_opt(ema_net, optimizer, save_ema_path, epoch+1)

#             if max_flag:
#                 save_net_opt(net, optimizer, save_path / 'best.pth', epoch+1)
#                 save_net_opt(ema_net, optimizer, save_path / 'best_ema.pth', epoch+1)

#         writer.flush()

# directories_to_copy = ['dataloader', 'networks', 'utils']  
# files_to_copy = ['train.py', 'README.md']

# destination_base = os.path.join(resultdir, 'codes')
# os.makedirs(destination_base, exist_ok=True)  

# # Copy directories
# for directory in directories_to_copy:
#     src_dir = os.path.join('.', directory)
#     dst_dir = os.path.join(destination_base, directory)
#     if os.path.exists(src_dir):
#         shutil.copytree(src_dir, dst_dir, ignore=shutil.ignore_patterns('.git', '__pycache__'))

# # Copy individual files
# for file_name in files_to_copy:
#     src_file = os.path.join('.', file_name)
#     dst_file = os.path.join(destination_base, file_name)
#     if os.path.exists(src_file):
#         shutil.copy2(src_file, dst_file)

# if __name__ == '__main__':
#     main()


import os
import time
from pathlib import Path
import numpy as np
from tqdm import tqdm
import logging
import sys
import argparse
import re
import shutil

import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
from tensorboardX import SummaryWriter
from torch.utils.data import DataLoader
from torch.nn.modules.loss import CrossEntropyLoss

from dataloader.AortaDissection import AortaDissection

import utils.loss
from utils import statistic, ramps
from utils.loss import DiceLoss, SoftIoULoss, to_one_hot
from utils.losses import FocalLoss
from utils.logger import get_cur_time,checkpoint_save
from utils.Generate_Prototype import *
from utils.train_util import *

from networks.vnet_AMC import VNet_AMC
from test import test_LA_Pancreas, test_AD


def get_arguments():
    parser = argparse.ArgumentParser(description='Semi-supervised Training for UPCoL: Uncertainty-informed Prototype Consistency Learning for Semi-supervised Medical Image Segmentation')

    # Model
    parser.add_argument('--num_classes', type=int, default=3, help='output channel of network')
    parser.add_argument('--exp', type=str, default='TBAD', help='experiment_name')
    parser.add_argument('--alpha', type=float, default=0.99, help='params in ema update')
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--load_path', type=str, default='/results/TBAD', help='Paths to previous checkpoints')

    # Dataset
    parser.add_argument("--data_dir", type=str, default='preprocess/TBAD/ImageTBAD', help="Path to the TBAD dataset.")
    parser.add_argument("--list_dir", type=str, default='datalist/AD/AD_0', help="Paths to cross-validated TBAD datasets, list of test sets and all training sets (including all labeled and unlabeled samples)")
    parser.add_argument("--save_path", type=str, default='/home/amishr17/aryan/new_attempt/results', help="Path to save training outputs.")
    parser.add_argument("--aug_times", type=int, default=1, help="times of augmentation for training.")

    # Optimization options
    parser.add_argument('--lab_batch_size', type=int, default=1, help='batch size')
    parser.add_argument('--unlab_batch_size', type=int, default=2, help='batch size')
    parser.add_argument('--lr', type=float, default=0.001, help='learning rate')
    parser.add_argument('--num_epochs', type=int, default=20, help='frequency of checkpoint save in pretraining')
    parser.add_argument('--consistency_rampup', type=float, default=300.0, help='consistency_rampup')
    parser.add_argument('--steps_per_epoch', type=int, default=1, help='number of steps per epoch')
    parser.add_argument('--save_step', type=int, default=1, help='frequency of checkpoint save in pretraining')

    parser.add_argument('--beta1', type=float, default=0.5, help='params of optimizer Adam')
    parser.add_argument('--beta2', type=float, default=0.999, help='params of optimizer Adam')
    parser.add_argument('--scaler', type=float, default=1, help='multiplier of prototype')
    
    # Miscs
    parser.add_argument('--gpu', type=str, default='0', help='GPU to use')
    parser.add_argument('--seed', type=int, default=1337, help='set the seed of random initialization')
    
    return parser.parse_args()
   

args = get_arguments()

# Use CUDA
os.environ['CUDA_VISIBLE_DEVICES'] = args.gpu
use_cuda = torch.cuda.is_available()

# create logger
resultdir = os.path.join(args.save_path, args.exp)
logdir = os.path.join(resultdir, 'logs')
savedir = os.path.join(resultdir, 'checkpoints')
shotdir = os.path.join(resultdir, 'snapshot')
print('Result path: {}\nLogs path: {}\nCheckpoints path: {}\nSnapshot path: {}'.format(resultdir, logdir, savedir, shotdir))

os.makedirs(logdir, exist_ok=True)
os.makedirs(savedir, exist_ok=True)
os.makedirs(shotdir, exist_ok=True)

writer = SummaryWriter(logdir)

logger = logging.getLogger()
logger.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s %(filename)s %(funcName)s [line:%(lineno)d] %(levelname)s %(message)s')

sh = logging.StreamHandler()
sh.setFormatter(formatter)
logger.addHandler(sh)

fh = logging.FileHandler(shotdir+'/'+'snapshot.log', encoding='utf8')
fh.setFormatter(formatter) 
logger.addHandler(fh)
logging.info(str(args))

def create_model(ema=False):
    net = nn.DataParallel(VNet_AMC(n_channels=1, n_classes=args.num_classes, n_branches=4))
    model = net.cuda()
    if ema:
        for param in model.parameters():
            param.detach_()
    return model

def create_dataloader():
    if 'LA' in args.data_dir:
        train_labset = LAHeart(args.data_dir,args.list_dir,split='lab', aug_times = args.aug_times)
        train_unlabset = LAHeart(args.data_dir,args.list_dir,split='unlab', aug_times = args.aug_times)
        testset = LAHeart(args.data_dir,args.list_dir,split='test')
    elif 'TBAD' in args.data_dir:
        train_labset = AortaDissection(args.data_dir,args.list_dir,split='lab', aug_times = args.aug_times)
        train_unlabset = AortaDissection(args.data_dir,args.list_dir,split='unlab', aug_times = args.aug_times)
        testset = AortaDissection(args.data_dir,args.list_dir,split='test', aug_times = args.aug_times)
    else:
        train_labset =Pancreas(args.data_dir, args.list_dir,split='lab', aug_times = args.aug_times)
        train_unlabset = Pancreas(args.data_dir,args.list_dir,split='unlab', aug_times = args.aug_times)
        testset = Pancreas(args.data_dir,args.list_dir,split='test', aug_times = args.aug_times) 
    
    trainlab_loader = DataLoader(train_labset, batch_size=args.lab_batch_size, shuffle=True, num_workers=0)
    trainunlab_loader = DataLoader(train_unlabset, batch_size=args.unlab_batch_size, shuffle=True, num_workers=0)
    test_loader = DataLoader(testset, batch_size=1, shuffle=False, num_workers=0)

    logging.info("{} iterations for lab per epoch.".format(len(trainlab_loader)))
    logging.info("{} iterations for unlab per epoch.".format(len(trainunlab_loader)))
    logging.info("{} samples for test.\n".format(len(test_loader)))
    return trainlab_loader, trainunlab_loader, test_loader

def main():
    save_path = Path(savedir)

    set_random_seed(args.seed)

    net = create_model().cuda()
    ema_net = create_model(ema=True).cuda()
    optimizer = optim.Adam(net.parameters(), lr=args.lr, betas=(args.beta1, args.beta2)) 
    if args.resume:
        load_net_opt(net, optimizer, Path(args.load_path) / 'best.pth')
        load_net_opt(ema_net, optimizer, Path(args.load_path) / 'best_ema.pth')

    trainlab_loader, trainunlab_loader, test_loader = create_dataloader()

    dice_loss = DiceLoss(nclass=args.num_classes)
    ce_loss = CrossEntropyLoss()
    focal_loss = FocalLoss()
    iou_loss = SoftIoULoss(nclass=args.num_classes)
    pixel_level_ce_loss = CrossEntropyLoss(reduction='none')

    maxdice = 0
    iter_num = 0

    for epoch in tqdm(range(args.num_epochs), ncols=70):
        logging.info('\n')

        net.train()
        for step, (labeled_batch, unlabeled_batch) in enumerate(zip(trainlab_loader,trainunlab_loader)):
            lab_img, lab_lab = labeled_batch['image'].cuda(), labeled_batch['label'].cuda()
            unlab_img = unlabeled_batch['image'].cuda()
            lab_lab_onehot = to_one_hot(lab_lab.unsqueeze(1), args.num_classes)

            '''Supervised'''
            lab_out = net(lab_img)

            lab_out_ce = lab_out[0]
            lab_out_dice = lab_out[1]
            lab_out_focal = lab_out[2]
            lab_out_iou = lab_out[3]

            loss_ce = ce_loss(lab_out_ce, lab_lab)
            loss_dice = dice_loss(lab_out_dice, lab_lab)
            loss_focal = focal_loss(lab_out_focal, lab_lab)
            loss_iou = ce_loss(lab_out_iou, lab_lab)

            loss_supervised = (loss_ce + loss_dice + loss_focal + loss_iou) / 4 

            # labeled prototypes
            lab_fts = F.interpolate(lab_out[4], size=lab_lab.shape[-3:],mode='trilinear')
            lab_prototypes = getPrototype(lab_fts, lab_lab_onehot)

            '''Unsupervised'''
            with torch.no_grad():
                unlab_ema_out = ema_net(unlab_img)
                unlab_ema_out_pred = (unlab_ema_out[0] + unlab_ema_out[1] + unlab_ema_out[2] + unlab_ema_out[3]) / 4

                unlab_ema_out_soft = torch.softmax(unlab_ema_out_pred, dim=1)
                unlab_ema_mask = torch.argmax(unlab_ema_out_soft, dim=1)
                unlab_ema_mask_onehot = to_one_hot(unlab_ema_mask.unsqueeze(1), args.num_classes)

                # uncertainty assesment
                uncertainty =  -torch.sum(unlab_ema_out_soft * torch.log(unlab_ema_out_soft  + 1e-16), dim=1)
                norm_uncertainty = torch.stack([uncertain / torch.sum(uncertain) for uncertain in uncertainty],dim=0)

                reliability_map = (1 - norm_uncertainty) / np.prod(np.array(norm_uncertainty.shape[-3:]))

                unlab_ema_fts = F.interpolate(unlab_ema_out[4], size=unlab_ema_mask.shape[-3:],mode='trilinear')
                unlab_prototypes = getPrototype(unlab_ema_fts, unlab_ema_mask_onehot, reliability_map)

                consistency_weight = get_current_consistency_weight(epoch, args.consistency_rampup)

            '''Prototype fusion'''
            prototypes = [ (lab_prototypes[c] + consistency_weight * unlab_prototypes[c]) / (1 + consistency_weight) for c in range(args.num_classes)]

            lab_dist =  torch.stack([calDist(lab_fts, prototype, scaler=args.scaler) for prototype in prototypes], dim=1)
            unlab_dist = torch.stack([calDist(unlab_ema_fts, prototype, scaler=args.scaler) for prototype in prototypes], dim=1)
                
            '''Prototype consistency learning'''
            loss_pc_lab = ce_loss(lab_dist,lab_lab)
            loss_pc_unlab = torch.sum(pixel_level_ce_loss(unlab_dist, unlab_ema_mask) * reliability_map)

            '''Total'''
            loss = loss_supervised + loss_pc_lab + consistency_weight * loss_pc_unlab

            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            update_ema_variables(net, ema_net, args.alpha, iter_num)
            iter_num += 1

            lab_masks = torch.softmax(lab_out_dice, dim = 1)
            lab_masks = torch.argmax(lab_masks, dim = 1)
            train_dice = statistic.dice_ratio(lab_masks, lab_lab)

            logging.info('epoch : %d, step : %d, loss_all: %.4f,'
                         'loss_ce: %.4f, loss_dice: %.4f, loss_focal: %.4f, loss_iou: %.4f, '
                         'loss_supervised: %.4f, loss_pc_lab: %.4f, '
                         'loss_pc_unlab: %.4f, train_dice: %.4f' % (
                            epoch+1, step, loss.item(), 
                            loss_ce.item(), loss_dice.item(), loss_focal.item(), loss_iou.item(),
                            loss_supervised.item(), loss_pc_lab.item(), loss_pc_unlab.item(), train_dice))           

            writer.add_scalar('info/loss_ce', loss_ce, iter_num)
            writer.add_scalar('info/loss_dice', loss_dice, iter_num)
            writer.add_scalar('info/loss_focal', loss_focal, iter_num)
            writer.add_scalar('info/loss_iou', loss_iou, iter_num)
            writer.add_scalar('info/loss_supervised', loss_supervised, iter_num)

            writer.add_scalar('info/loss_pc_lab', loss_pc_lab, iter_num)
            writer.add_scalar('info/loss_pc_unlab', loss_pc_unlab, iter_num)
            writer.add_scalar('info/consistency_weight', consistency_weight, iter_num)

            writer.add_scalar('info/loss_all', loss, iter_num)
            writer.add_scalar('val/train_dice', train_dice, iter_num)

        '''Test'''
        if (epoch+1) % args.save_step == 0:
            if 'TBAD' in args.data_dir:
                val_dice, maxdice, max_flag = test_AD(net, test_loader, args, maxdice)
            else:
                val_dice, maxdice, max_flag = test_LA_Pancreas(net, test_loader,args, maxdice)

            writer.add_scalar('val/test_dice', val_dice, epoch+1)

            save_mode_path = os.path.join(save_path,
                            'epoch_{}_iter_{}_dice_{}.pth'.format(
                                epoch+1, iter_num, round(val_dice, 4)))
            save_net_opt(net, optimizer, save_mode_path, epoch+1)

            save_ema_path = os.path.join(save_path,
                            'ema_epoch_{}_iter_{}_dice_{}.pth'.format(
                                epoch+1, iter_num, round(val_dice, 4)))
            save_net_opt(ema_net, optimizer, save_ema_path, epoch+1)


            if max_flag:
                save_net_opt(net, optimizer, save_path / 'best.pth', epoch+1)
                save_net_opt(ema_net, optimizer, save_path / 'best_ema.pth', epoch+1)

        writer.flush()

directories_to_copy = ['dataloader', 'networks', 'utils']  
files_to_copy = ['train.py', 'README.md']

destination_base = os.path.join(resultdir, 'codes')
os.makedirs(destination_base, exist_ok=True)  

# Copy directories
for directory in directories_to_copy:
    src_dir = os.path.join('.', directory)
    dst_dir = os.path.join(destination_base, directory)
    if os.path.exists(src_dir):
        shutil.copytree(src_dir, dst_dir, ignore=shutil.ignore_patterns('.git', '__pycache__'))

# Copy individual files
for file_name in files_to_copy:
    src_file = os.path.join('.', file_name)
    dst_file = os.path.join(destination_base, file_name)
    if os.path.exists(src_file):
        shutil.copy2(src_file, dst_file)

if __name__ == '__main__':
    main()
