import numpy as np
import pandas as pd
import pytorch_lightning as pl
import torch
from graphnet.models.graph_builders import KNNGraphBuilder
from sklearn.model_selection import StratifiedKFold
from torch_geometric.data import Dataset
from torch_geometric.loader import DataLoader

from src.config import INPUT_PATH


def create_folds(data, n_splits=5, random_state=48):
    data["n_pulses"] = data["last_pulse_index"] - data["first_pulse_index"]
    data["bins"] = pd.qcut(np.log10(data["n_pulses"]), 10, labels=False)
    data["fold"] = -1

    kf = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=random_state)

    for f, (t_, v_) in enumerate(kf.split(X=data, y=data["bins"])):
        data.loc[v_, "fold"] = f

    return data


class IceCubeDataset(Dataset):
    def __init__(self, df, transform=None, pre_transform=None, pre_filter=None):
        super().__init__(transform, pre_transform, pre_filter)
        self.df = df.reset_index(drop=True)  # DataFrame containing batch_id & event_id

    def len(self):
        return len(self.df)

    def get(self, idx):
        row = self.df.loc[idx]

        file_path = (
            INPUT_PATH
            / "train_events"
            / f"batch_{int(row['batch_id'])}"
            / f"event_{int(row['event_id'])}.pt"
        )

        data = torch.load(file_path)
        return data


class IceCubeDataModule(pl.LightningDataModule):
    def __init__(
        self,
        batch_size: int = 32,
        max_len: int = 2048,
        seed: int = 48,
        folds: int = 5,
        nearest_neighbours: int = 8,
        num_workers: int = 8,
        **kwargs,
    ):
        super().__init__()

        self.batch_size = batch_size
        self.max_len = max_len
        self.num_workers = num_workers
        self.df = pd.read_parquet(INPUT_PATH / "folds.parquet")
        self.train_steps = 0
        self.pre_transform = KNNGraphBuilder(nb_nearest_neighbours=nearest_neighbours)

    def setup(self, stage=None, fold_n: int = 0):
        trn_df = self.df.query(f"fold != {fold_n}")
        val_df = self.df.query(f"fold == {fold_n}")

        if stage == "fit" or stage is None:
            self.clr_train = IceCubeDataset(trn_df, pre_transform=self.pre_transform)
            self.clr_valid = IceCubeDataset(val_df, pre_transform=self.pre_transform)

        self.train_steps = len(self.clr_train) / self.batch_size
        print(len(self.clr_train), "train and", len(self.clr_valid), "valid samples")

    def train_dataloader(self):
        return DataLoader(
            self.clr_train,
            num_workers=self.num_workers,
            batch_size=self.batch_size,
            pin_memory=True,
        )

    def val_dataloader(self):
        return DataLoader(
            self.clr_valid,
            batch_size=self.batch_size,
            num_workers=self.num_workers,
            pin_memory=True,
        )

    def predict_dataloader(self):
        return DataLoader(
            self.clr_valid,
            batch_size=self.batch_size * 8,
            num_workers=self.num_workers,
        )


# if __name__ == "__main__":
#     import sys

#     COMP_NAME = "icecube-neutrinos-in-deep-ice"
#     sys.path.append(f"/home/anjum/kaggle/{COMP_NAME}/")

#     meta = pd.read_parquet(INPUT_PATH / "train_meta.parquet").query("batch_id == 1")
#     ds = IceCubeDataset(meta)
#     dl = DataLoader(ds, batch_size=4)

#     for d in dl:
#         print(d)
#         print(d.y.reshape(-1, 2))
#         break
