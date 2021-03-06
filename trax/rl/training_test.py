# coding=utf-8
# Copyright 2020 The Trax Authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# Lint as: python3
"""Tests for RL training."""

import functools
import math
import os
import pickle

from absl.testing import absltest
import tensorflow as tf

from trax import layers as tl
from trax import models
from trax import optimizers as opt
from trax import test_utils
from trax.rl import task as rl_task
from trax.rl import training
from trax.supervised import lr_schedules


class TrainingTest(absltest.TestCase):

  def setUp(self):
    super().setUp()
    test_utils.ensure_flag('test_tmpdir')
    self._model_fn = functools.partial(
        models.Policy,
        body=lambda mode: tl.Serial(  # pylint: disable=g-long-lambda
            tl.Dense(64), tl.Relu(), tl.Dense(64), tl.Relu()
        ),
    )

  def test_policy_gradient_smoke(self):
    """Check save and restore of policy agent."""
    task = rl_task.RLTask('CartPole-v0', max_steps=2)
    tmp_dir = self.create_tempdir().full_path
    agent = training.PolicyGradient(
        task,
        model_fn=self._model_fn,
        optimizer=opt.Adam,
        batch_size=2,
        n_trajectories_per_epoch=2,
        n_eval_episodes=1,
        output_dir=tmp_dir)
    agent.run(1)
    self.assertEqual(agent.current_epoch, 1)

  def test_policy_gradient_save_restore(self):
    """Check save and restore of policy agent."""
    task = rl_task.RLTask('CartPole-v0', max_steps=2)
    tmp_dir = self.create_tempdir().full_path
    agent1 = training.PolicyGradient(
        task,
        model_fn=self._model_fn,
        optimizer=opt.Adam,
        batch_size=2,
        n_trajectories_per_epoch=2,
        n_eval_episodes=1,
        output_dir=tmp_dir)
    agent1.run(1)
    agent1.run(1)
    self.assertEqual(agent1.current_epoch, 2)
    self.assertEqual(agent1.loop.step, 2)
    # Trainer 2 starts where agent 1 stopped.
    agent2 = training.PolicyGradient(
        task,
        model_fn=self._model_fn,
        optimizer=opt.Adam,
        batch_size=2,
        n_trajectories_per_epoch=2,
        n_eval_episodes=1,
        output_dir=tmp_dir)
    agent2.run(1)
    self.assertEqual(agent2.current_epoch, 3)
    self.assertEqual(agent2.loop.step, 3)
    # Manually set saved epoch to 1.
    dictionary = {'epoch': 1, 'avg_returns': [0.0],
                  'avg_returns_temperature0': {200: [0.0]}}
    with tf.io.gfile.GFile(os.path.join(tmp_dir, 'rl.pkl'), 'wb') as f:
      pickle.dump(dictionary, f)
    # Trainer 3 restores from a checkpoint with Agent/Loop step mistmatch,
    # should fail.
    def agent3_fn():
      return training.PolicyGradient(
          task,
          model_fn=self._model_fn,
          optimizer=opt.Adam,
          batch_size=2,
          n_trajectories_per_epoch=2,
          n_eval_episodes=1,
          output_dir=tmp_dir,
      )
    self.assertRaises(ValueError, agent3_fn)
    agent1.close()
    agent2.close()

  def test_policy_gradient_cartpole(self):
    """Trains a policy on cartpole."""
    task = rl_task.RLTask('CartPole-v0', max_steps=200)
    lr = lambda: lr_schedules.multifactor(constant=1e-2, factors='constant')
    max_avg_returns = -math.inf
    for _ in range(2):
      agent = training.PolicyGradient(
          task,
          model_fn=self._model_fn,
          optimizer=opt.Adam,
          lr_schedule=lr,
          batch_size=128,
          n_trajectories_per_epoch=2,
      )
      # Assert that we get to 200 at some point and then exit so the test is as
      # fast as possible.
      for ep in range(200):
        agent.run(1)
        self.assertEqual(agent.current_epoch, ep + 1)
        if agent.avg_returns[-1] == 200.0:
          return
      max_avg_returns = max(max_avg_returns, agent.avg_returns[-1])
    self.fail(
        'The expected score of 200 has not been reached. '
        'Maximum at end was {}.'.format(max_avg_returns)
    )


if __name__ == '__main__':
  absltest.main()
