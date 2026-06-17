\ Model multi_agent_many_to_many
\ LP format - for model browsing. Use MPS format to capture full model detail.
\ Signature: 0x64b76b60859344b3
Maximize multi-objectives
  target_directed_reward: Priority=2 Weight=1 AbsTol=0 RelTol=0
   0 u_61_agent0 + 0 u_62_agent0 + 0 u_63_agent0 + 0 u_61_agent1
   + 0 u_62_agent1 + 0 u_63_agent1 + 0 u_61_agent2 + 0 u_62_agent2
   + 0 u_63_agent2 + 0.0704225352112676 z_5_12_agent0
   + 0.0704225352112676 z_5_14_agent0 + 0.0704225352112676 z_5_18_agent0
   + 0.0704225352112676 z_5_25_agent0 + 0.028169014084507 z_5_27_agent0
   + 0.0704225352112676 z_5_34_agent0 + 0.0704225352112676 z_5_42_agent0
   + 0.1408450704225352 z_5_44_agent0 + 0.028169014084507 z_5_47_agent0
   + 0.1408450704225352 z_5_52_agent0 + 0.028169014084507 z_5_53_agent0
   + 0.2112676056338028 z_5_60_agent0 + 0.0704225352112676 z_5_12_agent1
   + 0.0704225352112676 z_5_14_agent1 + 0.0704225352112676 z_5_18_agent1
   + 0.0704225352112676 z_5_25_agent1 + 0.028169014084507 z_5_27_agent1
   + 0.0704225352112676 z_5_34_agent1 + 0.0704225352112676 z_5_42_agent1
   + 0.1408450704225352 z_5_44_agent1 + 0.028169014084507 z_5_47_agent1
   + 0.1408450704225352 z_5_52_agent1 + 0.028169014084507 z_5_53_agent1
   + 0.2112676056338028 z_5_60_agent1 + 0.0704225352112676 z_5_12_agent2
   + 0.0704225352112676 z_5_14_agent2 + 0.0704225352112676 z_5_18_agent2
   + 0.0704225352112676 z_5_25_agent2 + 0.028169014084507 z_5_27_agent2
   + 0.0704225352112676 z_5_34_agent2 + 0.0704225352112676 z_5_42_agent2
   + 0.1408450704225352 z_5_44_agent2 + 0.028169014084507 z_5_47_agent2
   + 0.1408450704225352 z_5_52_agent2 + 0.028169014084507 z_5_53_agent2
   + 0.2112676056338028 z_5_60_agent2
  target_directed_route_cost: Priority=1 Weight=1 AbsTol=0 RelTol=0
   - 0.00216007201954816 x_12_46_agent0 - 0.00247417156085223 x_14_46_agent0
   - 0.00344780726197111 x_18_46_agent0 - 0.001757791400523 x_25_46_agent0
   - 0.00151875509066747 x_27_31_agent0
   - 0.00151875509066747 x_31_27_agent0
   - 7.0253354481930813e-04 x_31_53_agent0
   - 0.00270519140909676 x_34_46_agent0
   - 7.9217216101513271e-04 x_42_46_agent0
   - 0.00192322201740472 x_44_55_agent0
   - 0.00216007201954816 x_46_12_agent0
   - 0.00247417156085223 x_46_14_agent0
   - 0.00344780726197111 x_46_18_agent0 - 0.001757791400523 x_46_25_agent0
   - 0.00270519140909676 x_46_34_agent0
   - 7.9217216101513271e-04 x_46_42_agent0
   - 0.00121923093411069 x_46_60_agent0
   - 0.00158215801431817 x_47_55_agent0
   - 0.00261555279290093 x_52_55_agent0
   - 7.0253354481930813e-04 x_53_31_agent0
   - 0.00192322201740472 x_55_44_agent0
   - 0.00158215801431817 x_55_47_agent0
   - 0.00261555279290093 x_55_52_agent0
   - 0.00121923093411069 x_60_46_agent0
   - 0.00216007201954816 x_12_46_agent1
   - 0.00247417156085223 x_14_46_agent1
   - 0.00344780726197111 x_18_46_agent1 - 0.001757791400523 x_25_46_agent1
   - 0.00151875509066747 x_27_31_agent1
   - 0.00151875509066747 x_31_27_agent1
   - 7.0253354481930813e-04 x_31_53_agent1
   - 0.00270519140909676 x_34_46_agent1
   - 7.9217216101513271e-04 x_42_46_agent1
   - 0.00192322201740472 x_44_55_agent1
   - 0.00216007201954816 x_46_12_agent1
   - 0.00247417156085223 x_46_14_agent1
   - 0.00344780726197111 x_46_18_agent1 - 0.001757791400523 x_46_25_agent1
   - 0.00270519140909676 x_46_34_agent1
   - 7.9217216101513271e-04 x_46_42_agent1
   - 0.00121923093411069 x_46_60_agent1
   - 0.00158215801431817 x_47_55_agent1
   - 0.00261555279290093 x_52_55_agent1
   - 7.0253354481930813e-04 x_53_31_agent1
   - 0.00192322201740472 x_55_44_agent1
   - 0.00158215801431817 x_55_47_agent1
   - 0.00261555279290093 x_55_52_agent1
   - 0.00121923093411069 x_60_46_agent1
   - 0.00216007201954816 x_12_46_agent2
   - 0.00247417156085223 x_14_46_agent2
   - 0.00344780726197111 x_18_46_agent2 - 0.001757791400523 x_25_46_agent2
   - 0.00151875509066747 x_27_31_agent2
   - 0.00151875509066747 x_31_27_agent2
   - 7.0253354481930813e-04 x_31_53_agent2
   - 0.00270519140909676 x_34_46_agent2
   - 7.9217216101513271e-04 x_42_46_agent2
   - 0.00192322201740472 x_44_55_agent2
   - 0.00216007201954816 x_46_12_agent2
   - 0.00247417156085223 x_46_14_agent2
   - 0.00344780726197111 x_46_18_agent2 - 0.001757791400523 x_46_25_agent2
   - 0.00270519140909676 x_46_34_agent2
   - 7.9217216101513271e-04 x_46_42_agent2
   - 0.00121923093411069 x_46_60_agent2
   - 0.00158215801431817 x_47_55_agent2
   - 0.00261555279290093 x_52_55_agent2
   - 7.0253354481930813e-04 x_53_31_agent2
   - 0.00192322201740472 x_55_44_agent2
   - 0.00158215801431817 x_55_47_agent2
   - 0.00261555279290093 x_55_52_agent2
   - 0.00121923093411069 x_60_46_agent2 - 0.05 y_31_agent0
   - 0.05 y_55_agent0 - 0.05 y_31_agent1 - 0.05 y_46_agent1
   - 0.05 y_46_agent2 - 0.05 y_55_agent2 + 0.00307686372015261 Constant1
Subject To
 depart_agent0: x_46_12_agent0 + x_46_14_agent0 + x_46_18_agent0
   + x_46_25_agent0 + x_46_34_agent0 + x_46_42_agent0 + x_46_60_agent0 = 1
 first_hop_vp_agent0: x_46_12_agent0 + x_46_14_agent0 + x_46_18_agent0
   + x_46_25_agent0 + x_46_34_agent0 + x_46_42_agent0 + x_46_60_agent0 = 1
 first_hop_grounded_vv_agent0: x_46_12_agent0 + x_46_14_agent0
   + x_46_18_agent0 + x_46_25_agent0 + x_46_34_agent0 + x_46_42_agent0
   + x_46_60_agent0 = 1
 no_return_agent0: x_12_46_agent0 + x_14_46_agent0 + x_18_46_agent0
   + x_25_46_agent0 + x_34_46_agent0 + x_42_46_agent0 + x_60_46_agent0 = 0
 flow_in_12_agent0: x_46_12_agent0 - y_12_agent0 = 0
 flow_out_12_agent0: x_12_46_agent0 - y_12_agent0 <= 0
 flow_in_14_agent0: x_46_14_agent0 - y_14_agent0 = 0
 flow_out_14_agent0: x_14_46_agent0 - y_14_agent0 <= 0
 flow_in_18_agent0: x_46_18_agent0 - y_18_agent0 = 0
 flow_out_18_agent0: x_18_46_agent0 - y_18_agent0 <= 0
 flow_in_25_agent0: x_46_25_agent0 - y_25_agent0 = 0
 flow_out_25_agent0: x_25_46_agent0 - y_25_agent0 <= 0
 flow_in_27_agent0: x_31_27_agent0 - y_27_agent0 = 0
 flow_out_27_agent0: x_27_31_agent0 - y_27_agent0 <= 0
 flow_in_31_agent0: x_27_31_agent0 + x_53_31_agent0 - y_31_agent0 = 0
 flow_out_31_agent0: x_31_27_agent0 + x_31_53_agent0 - y_31_agent0 <= 0
 flow_in_34_agent0: x_46_34_agent0 - y_34_agent0 = 0
 flow_out_34_agent0: x_34_46_agent0 - y_34_agent0 <= 0
 flow_in_42_agent0: x_46_42_agent0 - y_42_agent0 = 0
 flow_out_42_agent0: x_42_46_agent0 - y_42_agent0 <= 0
 flow_in_44_agent0: x_55_44_agent0 - y_44_agent0 = 0
 flow_out_44_agent0: x_44_55_agent0 - y_44_agent0 <= 0
 flow_in_47_agent0: x_55_47_agent0 - y_47_agent0 = 0
 flow_out_47_agent0: x_47_55_agent0 - y_47_agent0 <= 0
 flow_in_52_agent0: x_55_52_agent0 - y_52_agent0 = 0
 flow_out_52_agent0: x_52_55_agent0 - y_52_agent0 <= 0
 flow_in_53_agent0: x_31_53_agent0 - y_53_agent0 = 0
 flow_out_53_agent0: x_53_31_agent0 - y_53_agent0 <= 0
 flow_in_55_agent0: x_44_55_agent0 + x_47_55_agent0 + x_52_55_agent0
   - y_55_agent0 = 0
 flow_out_55_agent0: x_55_44_agent0 + x_55_47_agent0 + x_55_52_agent0
   - y_55_agent0 <= 0
 flow_in_60_agent0: x_46_60_agent0 - y_60_agent0 = 0
 flow_out_60_agent0: x_60_46_agent0 - y_60_agent0 <= 0
 flow_in_61_agent0: - y_61_agent0 = 0
 flow_out_61_agent0: - y_61_agent0 <= 0
 flow_in_62_agent0: - y_62_agent0 = 0
 flow_out_62_agent0: - y_62_agent0 <= 0
 flow_in_63_agent0: - y_63_agent0 = 0
 flow_out_63_agent0: - y_63_agent0 <= 0
 target_reward_visit_5_12_agent0: - y_12_agent0 + z_5_12_agent0 <= 0
 target_reward_visit_5_14_agent0: - y_14_agent0 + z_5_14_agent0 <= 0
 target_reward_visit_5_18_agent0: - y_18_agent0 + z_5_18_agent0 <= 0
 target_reward_visit_5_25_agent0: - y_25_agent0 + z_5_25_agent0 <= 0
 target_reward_visit_5_27_agent0: - y_27_agent0 + z_5_27_agent0 <= 0
 target_reward_visit_5_34_agent0: - y_34_agent0 + z_5_34_agent0 <= 0
 target_reward_visit_5_42_agent0: - y_42_agent0 + z_5_42_agent0 <= 0
 target_reward_visit_5_44_agent0: - y_44_agent0 + z_5_44_agent0 <= 0
 target_reward_visit_5_47_agent0: - y_47_agent0 + z_5_47_agent0 <= 0
 target_reward_visit_5_52_agent0: - y_52_agent0 + z_5_52_agent0 <= 0
 target_reward_visit_5_53_agent0: - y_53_agent0 + z_5_53_agent0 <= 0
 target_reward_visit_5_60_agent0: - y_60_agent0 + z_5_60_agent0 <= 0
 mtz_12_46_agent0: 18 x_12_46_agent0 + u_12_agent0 - u_46_agent0 <= 17
 mtz_14_46_agent0: 18 x_14_46_agent0 + u_14_agent0 - u_46_agent0 <= 17
 mtz_18_46_agent0: 18 x_18_46_agent0 + u_18_agent0 - u_46_agent0 <= 17
 mtz_25_46_agent0: 18 x_25_46_agent0 + u_25_agent0 - u_46_agent0 <= 17
 mtz_27_31_agent0: 18 x_27_31_agent0 + u_27_agent0 - u_31_agent0 <= 17
 mtz_31_27_agent0: 18 x_31_27_agent0 - u_27_agent0 + u_31_agent0 <= 17
 mtz_31_53_agent0: 18 x_31_53_agent0 + u_31_agent0 - u_53_agent0 <= 17
 mtz_34_46_agent0: 18 x_34_46_agent0 + u_34_agent0 - u_46_agent0 <= 17
 mtz_42_46_agent0: 18 x_42_46_agent0 + u_42_agent0 - u_46_agent0 <= 17
 mtz_44_55_agent0: 18 x_44_55_agent0 + u_44_agent0 - u_55_agent0 <= 17
 mtz_46_12_agent0: 18 x_46_12_agent0 - u_12_agent0 + u_46_agent0 <= 17
 mtz_46_14_agent0: 18 x_46_14_agent0 - u_14_agent0 + u_46_agent0 <= 17
 mtz_46_18_agent0: 18 x_46_18_agent0 - u_18_agent0 + u_46_agent0 <= 17
 mtz_46_25_agent0: 18 x_46_25_agent0 - u_25_agent0 + u_46_agent0 <= 17
 mtz_46_34_agent0: 18 x_46_34_agent0 - u_34_agent0 + u_46_agent0 <= 17
 mtz_46_42_agent0: 18 x_46_42_agent0 - u_42_agent0 + u_46_agent0 <= 17
 mtz_46_60_agent0: 18 x_46_60_agent0 + u_46_agent0 - u_60_agent0 <= 17
 mtz_47_55_agent0: 18 x_47_55_agent0 + u_47_agent0 - u_55_agent0 <= 17
 mtz_52_55_agent0: 18 x_52_55_agent0 + u_52_agent0 - u_55_agent0 <= 17
 mtz_53_31_agent0: 18 x_53_31_agent0 - u_31_agent0 + u_53_agent0 <= 17
 mtz_55_44_agent0: 18 x_55_44_agent0 - u_44_agent0 + u_55_agent0 <= 17
 mtz_55_47_agent0: 18 x_55_47_agent0 - u_47_agent0 + u_55_agent0 <= 17
 mtz_55_52_agent0: 18 x_55_52_agent0 - u_52_agent0 + u_55_agent0 <= 17
 mtz_60_46_agent0: 18 x_60_46_agent0 - u_46_agent0 + u_60_agent0 <= 17
 depart_agent1: x_55_44_agent1 + x_55_47_agent1 + x_55_52_agent1 = 1
 first_hop_vp_agent1: x_55_44_agent1 + x_55_47_agent1 + x_55_52_agent1 = 1
 first_hop_grounded_vv_agent1: x_55_44_agent1 + x_55_47_agent1
   + x_55_52_agent1 = 1
 no_return_agent1: x_44_55_agent1 + x_47_55_agent1 + x_52_55_agent1 = 0
 flow_in_12_agent1: x_46_12_agent1 - y_12_agent1 = 0
 flow_out_12_agent1: x_12_46_agent1 - y_12_agent1 <= 0
 flow_in_14_agent1: x_46_14_agent1 - y_14_agent1 = 0
 flow_out_14_agent1: x_14_46_agent1 - y_14_agent1 <= 0
 flow_in_18_agent1: x_46_18_agent1 - y_18_agent1 = 0
 flow_out_18_agent1: x_18_46_agent1 - y_18_agent1 <= 0
 flow_in_25_agent1: x_46_25_agent1 - y_25_agent1 = 0
 flow_out_25_agent1: x_25_46_agent1 - y_25_agent1 <= 0
 flow_in_27_agent1: x_31_27_agent1 - y_27_agent1 = 0
 flow_out_27_agent1: x_27_31_agent1 - y_27_agent1 <= 0
 flow_in_31_agent1: x_27_31_agent1 + x_53_31_agent1 - y_31_agent1 = 0
 flow_out_31_agent1: x_31_27_agent1 + x_31_53_agent1 - y_31_agent1 <= 0
 flow_in_34_agent1: x_46_34_agent1 - y_34_agent1 = 0
 flow_out_34_agent1: x_34_46_agent1 - y_34_agent1 <= 0
 flow_in_42_agent1: x_46_42_agent1 - y_42_agent1 = 0
 flow_out_42_agent1: x_42_46_agent1 - y_42_agent1 <= 0
 flow_in_44_agent1: x_55_44_agent1 - y_44_agent1 = 0
 flow_out_44_agent1: x_44_55_agent1 - y_44_agent1 <= 0
 flow_in_46_agent1: x_12_46_agent1 + x_14_46_agent1 + x_18_46_agent1
   + x_25_46_agent1 + x_34_46_agent1 + x_42_46_agent1 + x_60_46_agent1
   - y_46_agent1 = 0
 flow_out_46_agent1: x_46_12_agent1 + x_46_14_agent1 + x_46_18_agent1
   + x_46_25_agent1 + x_46_34_agent1 + x_46_42_agent1 + x_46_60_agent1
   - y_46_agent1 <= 0
 flow_in_47_agent1: x_55_47_agent1 - y_47_agent1 = 0
 flow_out_47_agent1: x_47_55_agent1 - y_47_agent1 <= 0
 flow_in_52_agent1: x_55_52_agent1 - y_52_agent1 = 0
 flow_out_52_agent1: x_52_55_agent1 - y_52_agent1 <= 0
 flow_in_53_agent1: x_31_53_agent1 - y_53_agent1 = 0
 flow_out_53_agent1: x_53_31_agent1 - y_53_agent1 <= 0
 flow_in_60_agent1: x_46_60_agent1 - y_60_agent1 = 0
 flow_out_60_agent1: x_60_46_agent1 - y_60_agent1 <= 0
 flow_in_61_agent1: - y_61_agent1 = 0
 flow_out_61_agent1: - y_61_agent1 <= 0
 flow_in_62_agent1: - y_62_agent1 = 0
 flow_out_62_agent1: - y_62_agent1 <= 0
 flow_in_63_agent1: - y_63_agent1 = 0
 flow_out_63_agent1: - y_63_agent1 <= 0
 target_reward_visit_5_12_agent1: - y_12_agent1 + z_5_12_agent1 <= 0
 target_reward_visit_5_14_agent1: - y_14_agent1 + z_5_14_agent1 <= 0
 target_reward_visit_5_18_agent1: - y_18_agent1 + z_5_18_agent1 <= 0
 target_reward_visit_5_25_agent1: - y_25_agent1 + z_5_25_agent1 <= 0
 target_reward_visit_5_27_agent1: - y_27_agent1 + z_5_27_agent1 <= 0
 target_reward_visit_5_34_agent1: - y_34_agent1 + z_5_34_agent1 <= 0
 target_reward_visit_5_42_agent1: - y_42_agent1 + z_5_42_agent1 <= 0
 target_reward_visit_5_44_agent1: - y_44_agent1 + z_5_44_agent1 <= 0
 target_reward_visit_5_47_agent1: - y_47_agent1 + z_5_47_agent1 <= 0
 target_reward_visit_5_52_agent1: - y_52_agent1 + z_5_52_agent1 <= 0
 target_reward_visit_5_53_agent1: - y_53_agent1 + z_5_53_agent1 <= 0
 target_reward_visit_5_60_agent1: - y_60_agent1 + z_5_60_agent1 <= 0
 mtz_12_46_agent1: 18 x_12_46_agent1 + u_12_agent1 - u_46_agent1 <= 17
 mtz_14_46_agent1: 18 x_14_46_agent1 + u_14_agent1 - u_46_agent1 <= 17
 mtz_18_46_agent1: 18 x_18_46_agent1 + u_18_agent1 - u_46_agent1 <= 17
 mtz_25_46_agent1: 18 x_25_46_agent1 + u_25_agent1 - u_46_agent1 <= 17
 mtz_27_31_agent1: 18 x_27_31_agent1 + u_27_agent1 - u_31_agent1 <= 17
 mtz_31_27_agent1: 18 x_31_27_agent1 - u_27_agent1 + u_31_agent1 <= 17
 mtz_31_53_agent1: 18 x_31_53_agent1 + u_31_agent1 - u_53_agent1 <= 17
 mtz_34_46_agent1: 18 x_34_46_agent1 + u_34_agent1 - u_46_agent1 <= 17
 mtz_42_46_agent1: 18 x_42_46_agent1 + u_42_agent1 - u_46_agent1 <= 17
 mtz_44_55_agent1: 18 x_44_55_agent1 + u_44_agent1 - u_55_agent1 <= 17
 mtz_46_12_agent1: 18 x_46_12_agent1 - u_12_agent1 + u_46_agent1 <= 17
 mtz_46_14_agent1: 18 x_46_14_agent1 - u_14_agent1 + u_46_agent1 <= 17
 mtz_46_18_agent1: 18 x_46_18_agent1 - u_18_agent1 + u_46_agent1 <= 17
 mtz_46_25_agent1: 18 x_46_25_agent1 - u_25_agent1 + u_46_agent1 <= 17
 mtz_46_34_agent1: 18 x_46_34_agent1 - u_34_agent1 + u_46_agent1 <= 17
 mtz_46_42_agent1: 18 x_46_42_agent1 - u_42_agent1 + u_46_agent1 <= 17
 mtz_46_60_agent1: 18 x_46_60_agent1 + u_46_agent1 - u_60_agent1 <= 17
 mtz_47_55_agent1: 18 x_47_55_agent1 + u_47_agent1 - u_55_agent1 <= 17
 mtz_52_55_agent1: 18 x_52_55_agent1 + u_52_agent1 - u_55_agent1 <= 17
 mtz_53_31_agent1: 18 x_53_31_agent1 - u_31_agent1 + u_53_agent1 <= 17
 mtz_55_44_agent1: 18 x_55_44_agent1 - u_44_agent1 + u_55_agent1 <= 17
 mtz_55_47_agent1: 18 x_55_47_agent1 - u_47_agent1 + u_55_agent1 <= 17
 mtz_55_52_agent1: 18 x_55_52_agent1 - u_52_agent1 + u_55_agent1 <= 17
 mtz_60_46_agent1: 18 x_60_46_agent1 - u_46_agent1 + u_60_agent1 <= 17
 depart_agent2: x_31_27_agent2 + x_31_53_agent2 = 1
 first_hop_vp_agent2: x_31_27_agent2 + x_31_53_agent2 = 1
 first_hop_grounded_vv_agent2: x_31_27_agent2 + x_31_53_agent2 = 1
 no_return_agent2: x_27_31_agent2 + x_53_31_agent2 = 0
 flow_in_12_agent2: x_46_12_agent2 - y_12_agent2 = 0
 flow_out_12_agent2: x_12_46_agent2 - y_12_agent2 <= 0
 flow_in_14_agent2: x_46_14_agent2 - y_14_agent2 = 0
 flow_out_14_agent2: x_14_46_agent2 - y_14_agent2 <= 0
 flow_in_18_agent2: x_46_18_agent2 - y_18_agent2 = 0
 flow_out_18_agent2: x_18_46_agent2 - y_18_agent2 <= 0
 flow_in_25_agent2: x_46_25_agent2 - y_25_agent2 = 0
 flow_out_25_agent2: x_25_46_agent2 - y_25_agent2 <= 0
 flow_in_27_agent2: x_31_27_agent2 - y_27_agent2 = 0
 flow_out_27_agent2: x_27_31_agent2 - y_27_agent2 <= 0
 flow_in_34_agent2: x_46_34_agent2 - y_34_agent2 = 0
 flow_out_34_agent2: x_34_46_agent2 - y_34_agent2 <= 0
 flow_in_42_agent2: x_46_42_agent2 - y_42_agent2 = 0
 flow_out_42_agent2: x_42_46_agent2 - y_42_agent2 <= 0
 flow_in_44_agent2: x_55_44_agent2 - y_44_agent2 = 0
 flow_out_44_agent2: x_44_55_agent2 - y_44_agent2 <= 0
 flow_in_46_agent2: x_12_46_agent2 + x_14_46_agent2 + x_18_46_agent2
   + x_25_46_agent2 + x_34_46_agent2 + x_42_46_agent2 + x_60_46_agent2
   - y_46_agent2 = 0
 flow_out_46_agent2: x_46_12_agent2 + x_46_14_agent2 + x_46_18_agent2
   + x_46_25_agent2 + x_46_34_agent2 + x_46_42_agent2 + x_46_60_agent2
   - y_46_agent2 <= 0
 flow_in_47_agent2: x_55_47_agent2 - y_47_agent2 = 0
 flow_out_47_agent2: x_47_55_agent2 - y_47_agent2 <= 0
 flow_in_52_agent2: x_55_52_agent2 - y_52_agent2 = 0
 flow_out_52_agent2: x_52_55_agent2 - y_52_agent2 <= 0
 flow_in_53_agent2: x_31_53_agent2 - y_53_agent2 = 0
 flow_out_53_agent2: x_53_31_agent2 - y_53_agent2 <= 0
 flow_in_55_agent2: x_44_55_agent2 + x_47_55_agent2 + x_52_55_agent2
   - y_55_agent2 = 0
 flow_out_55_agent2: x_55_44_agent2 + x_55_47_agent2 + x_55_52_agent2
   - y_55_agent2 <= 0
 flow_in_60_agent2: x_46_60_agent2 - y_60_agent2 = 0
 flow_out_60_agent2: x_60_46_agent2 - y_60_agent2 <= 0
 flow_in_61_agent2: - y_61_agent2 = 0
 flow_out_61_agent2: - y_61_agent2 <= 0
 flow_in_62_agent2: - y_62_agent2 = 0
 flow_out_62_agent2: - y_62_agent2 <= 0
 flow_in_63_agent2: - y_63_agent2 = 0
 flow_out_63_agent2: - y_63_agent2 <= 0
 target_reward_visit_5_12_agent2: - y_12_agent2 + z_5_12_agent2 <= 0
 target_reward_visit_5_14_agent2: - y_14_agent2 + z_5_14_agent2 <= 0
 target_reward_visit_5_18_agent2: - y_18_agent2 + z_5_18_agent2 <= 0
 target_reward_visit_5_25_agent2: - y_25_agent2 + z_5_25_agent2 <= 0
 target_reward_visit_5_27_agent2: - y_27_agent2 + z_5_27_agent2 <= 0
 target_reward_visit_5_34_agent2: - y_34_agent2 + z_5_34_agent2 <= 0
 target_reward_visit_5_42_agent2: - y_42_agent2 + z_5_42_agent2 <= 0
 target_reward_visit_5_44_agent2: - y_44_agent2 + z_5_44_agent2 <= 0
 target_reward_visit_5_47_agent2: - y_47_agent2 + z_5_47_agent2 <= 0
 target_reward_visit_5_52_agent2: - y_52_agent2 + z_5_52_agent2 <= 0
 target_reward_visit_5_53_agent2: - y_53_agent2 + z_5_53_agent2 <= 0
 target_reward_visit_5_60_agent2: - y_60_agent2 + z_5_60_agent2 <= 0
 mtz_12_46_agent2: 18 x_12_46_agent2 + u_12_agent2 - u_46_agent2 <= 17
 mtz_14_46_agent2: 18 x_14_46_agent2 + u_14_agent2 - u_46_agent2 <= 17
 mtz_18_46_agent2: 18 x_18_46_agent2 + u_18_agent2 - u_46_agent2 <= 17
 mtz_25_46_agent2: 18 x_25_46_agent2 + u_25_agent2 - u_46_agent2 <= 17
 mtz_27_31_agent2: 18 x_27_31_agent2 + u_27_agent2 - u_31_agent2 <= 17
 mtz_31_27_agent2: 18 x_31_27_agent2 - u_27_agent2 + u_31_agent2 <= 17
 mtz_31_53_agent2: 18 x_31_53_agent2 + u_31_agent2 - u_53_agent2 <= 17
 mtz_34_46_agent2: 18 x_34_46_agent2 + u_34_agent2 - u_46_agent2 <= 17
 mtz_42_46_agent2: 18 x_42_46_agent2 + u_42_agent2 - u_46_agent2 <= 17
 mtz_44_55_agent2: 18 x_44_55_agent2 + u_44_agent2 - u_55_agent2 <= 17
 mtz_46_12_agent2: 18 x_46_12_agent2 - u_12_agent2 + u_46_agent2 <= 17
 mtz_46_14_agent2: 18 x_46_14_agent2 - u_14_agent2 + u_46_agent2 <= 17
 mtz_46_18_agent2: 18 x_46_18_agent2 - u_18_agent2 + u_46_agent2 <= 17
 mtz_46_25_agent2: 18 x_46_25_agent2 - u_25_agent2 + u_46_agent2 <= 17
 mtz_46_34_agent2: 18 x_46_34_agent2 - u_34_agent2 + u_46_agent2 <= 17
 mtz_46_42_agent2: 18 x_46_42_agent2 - u_42_agent2 + u_46_agent2 <= 17
 mtz_46_60_agent2: 18 x_46_60_agent2 + u_46_agent2 - u_60_agent2 <= 17
 mtz_47_55_agent2: 18 x_47_55_agent2 + u_47_agent2 - u_55_agent2 <= 17
 mtz_52_55_agent2: 18 x_52_55_agent2 + u_52_agent2 - u_55_agent2 <= 17
 mtz_53_31_agent2: 18 x_53_31_agent2 - u_31_agent2 + u_53_agent2 <= 17
 mtz_55_44_agent2: 18 x_55_44_agent2 - u_44_agent2 + u_55_agent2 <= 17
 mtz_55_47_agent2: 18 x_55_47_agent2 - u_47_agent2 + u_55_agent2 <= 17
 mtz_55_52_agent2: 18 x_55_52_agent2 - u_52_agent2 + u_55_agent2 <= 17
 mtz_60_46_agent2: 18 x_60_46_agent2 - u_46_agent2 + u_60_agent2 <= 17
 target_reward_unique_5: z_5_12_agent0 + z_5_14_agent0 + z_5_18_agent0
   + z_5_25_agent0 + z_5_27_agent0 + z_5_34_agent0 + z_5_42_agent0
   + z_5_44_agent0 + z_5_47_agent0 + z_5_52_agent0 + z_5_53_agent0
   + z_5_60_agent0 + z_5_12_agent1 + z_5_14_agent1 + z_5_18_agent1
   + z_5_25_agent1 + z_5_27_agent1 + z_5_34_agent1 + z_5_42_agent1
   + z_5_44_agent1 + z_5_47_agent1 + z_5_52_agent1 + z_5_53_agent1
   + z_5_60_agent1 + z_5_12_agent2 + z_5_14_agent2 + z_5_18_agent2
   + z_5_25_agent2 + z_5_27_agent2 + z_5_34_agent2 + z_5_42_agent2
   + z_5_44_agent2 + z_5_47_agent2 + z_5_52_agent2 + z_5_53_agent2
   + z_5_60_agent2 = 1
 unique_action_agent0_agent1_12: x_46_12_agent0 <= 1
 unique_action_agent0_agent1_14: x_46_14_agent0 <= 1
 unique_action_agent0_agent1_18: x_46_18_agent0 <= 1
 unique_action_agent0_agent1_25: x_46_25_agent0 <= 1
 unique_action_agent0_agent1_27: <= 1
 unique_action_agent0_agent1_31: <= 1
 unique_action_agent0_agent1_34: x_46_34_agent0 <= 1
 unique_action_agent0_agent1_42: x_46_42_agent0 <= 1
 unique_action_agent0_agent1_44: x_55_44_agent1 <= 1
 unique_action_agent0_agent1_46: <= 1
 unique_action_agent0_agent1_47: x_55_47_agent1 <= 1
 unique_action_agent0_agent1_52: x_55_52_agent1 <= 1
 unique_action_agent0_agent1_53: <= 1
 unique_action_agent0_agent1_55: <= 1
 unique_action_agent0_agent1_60: x_46_60_agent0 <= 1
 unique_action_agent0_agent2_12: x_46_12_agent0 <= 1
 unique_action_agent0_agent2_14: x_46_14_agent0 <= 1
 unique_action_agent0_agent2_18: x_46_18_agent0 <= 1
 unique_action_agent0_agent2_25: x_46_25_agent0 <= 1
 unique_action_agent0_agent2_27: x_31_27_agent2 <= 1
 unique_action_agent0_agent2_31: <= 1
 unique_action_agent0_agent2_34: x_46_34_agent0 <= 1
 unique_action_agent0_agent2_42: x_46_42_agent0 <= 1
 unique_action_agent0_agent2_44: <= 1
 unique_action_agent0_agent2_46: <= 1
 unique_action_agent0_agent2_47: <= 1
 unique_action_agent0_agent2_52: <= 1
 unique_action_agent0_agent2_53: x_31_53_agent2 <= 1
 unique_action_agent0_agent2_55: <= 1
 unique_action_agent0_agent2_60: x_46_60_agent0 <= 1
 unique_action_agent1_agent2_12: <= 1
 unique_action_agent1_agent2_14: <= 1
 unique_action_agent1_agent2_18: <= 1
 unique_action_agent1_agent2_25: <= 1
 unique_action_agent1_agent2_27: x_31_27_agent2 <= 1
 unique_action_agent1_agent2_31: <= 1
 unique_action_agent1_agent2_34: <= 1
 unique_action_agent1_agent2_42: <= 1
 unique_action_agent1_agent2_44: x_55_44_agent1 <= 1
 unique_action_agent1_agent2_46: <= 1
 unique_action_agent1_agent2_47: x_55_47_agent1 <= 1
 unique_action_agent1_agent2_52: x_55_52_agent1 <= 1
 unique_action_agent1_agent2_53: x_31_53_agent2 <= 1
 unique_action_agent1_agent2_55: <= 1
 unique_action_agent1_agent2_60: <= 1
Bounds
 1 <= u_12_agent0 <= 18
 1 <= u_14_agent0 <= 18
 1 <= u_18_agent0 <= 18
 1 <= u_25_agent0 <= 18
 1 <= u_27_agent0 <= 18
 1 <= u_31_agent0 <= 18
 1 <= u_34_agent0 <= 18
 1 <= u_42_agent0 <= 18
 1 <= u_44_agent0 <= 18
 1 <= u_46_agent0 <= 18
 1 <= u_47_agent0 <= 18
 1 <= u_52_agent0 <= 18
 1 <= u_53_agent0 <= 18
 1 <= u_55_agent0 <= 18
 1 <= u_60_agent0 <= 18
 1 <= u_61_agent0 <= 18
 1 <= u_62_agent0 <= 18
 1 <= u_63_agent0 <= 18
 1 <= u_12_agent1 <= 18
 1 <= u_14_agent1 <= 18
 1 <= u_18_agent1 <= 18
 1 <= u_25_agent1 <= 18
 1 <= u_27_agent1 <= 18
 1 <= u_31_agent1 <= 18
 1 <= u_34_agent1 <= 18
 1 <= u_42_agent1 <= 18
 1 <= u_44_agent1 <= 18
 1 <= u_46_agent1 <= 18
 1 <= u_47_agent1 <= 18
 1 <= u_52_agent1 <= 18
 1 <= u_53_agent1 <= 18
 1 <= u_55_agent1 <= 18
 1 <= u_60_agent1 <= 18
 1 <= u_61_agent1 <= 18
 1 <= u_62_agent1 <= 18
 1 <= u_63_agent1 <= 18
 1 <= u_12_agent2 <= 18
 1 <= u_14_agent2 <= 18
 1 <= u_18_agent2 <= 18
 1 <= u_25_agent2 <= 18
 1 <= u_27_agent2 <= 18
 1 <= u_31_agent2 <= 18
 1 <= u_34_agent2 <= 18
 1 <= u_42_agent2 <= 18
 1 <= u_44_agent2 <= 18
 1 <= u_46_agent2 <= 18
 1 <= u_47_agent2 <= 18
 1 <= u_52_agent2 <= 18
 1 <= u_53_agent2 <= 18
 1 <= u_55_agent2 <= 18
 1 <= u_60_agent2 <= 18
 1 <= u_61_agent2 <= 18
 1 <= u_62_agent2 <= 18
 1 <= u_63_agent2 <= 18
 Constant1 = 1
Binaries
 x_12_46_agent0 x_14_46_agent0 x_18_46_agent0 x_25_46_agent0 x_27_31_agent0
 x_31_27_agent0 x_31_53_agent0 x_34_46_agent0 x_42_46_agent0 x_44_55_agent0
 x_46_12_agent0 x_46_14_agent0 x_46_18_agent0 x_46_25_agent0 x_46_34_agent0
 x_46_42_agent0 x_46_60_agent0 x_47_55_agent0 x_52_55_agent0 x_53_31_agent0
 x_55_44_agent0 x_55_47_agent0 x_55_52_agent0 x_60_46_agent0 x_12_46_agent1
 x_14_46_agent1 x_18_46_agent1 x_25_46_agent1 x_27_31_agent1 x_31_27_agent1
 x_31_53_agent1 x_34_46_agent1 x_42_46_agent1 x_44_55_agent1 x_46_12_agent1
 x_46_14_agent1 x_46_18_agent1 x_46_25_agent1 x_46_34_agent1 x_46_42_agent1
 x_46_60_agent1 x_47_55_agent1 x_52_55_agent1 x_53_31_agent1 x_55_44_agent1
 x_55_47_agent1 x_55_52_agent1 x_60_46_agent1 x_12_46_agent2 x_14_46_agent2
 x_18_46_agent2 x_25_46_agent2 x_27_31_agent2 x_31_27_agent2 x_31_53_agent2
 x_34_46_agent2 x_42_46_agent2 x_44_55_agent2 x_46_12_agent2 x_46_14_agent2
 x_46_18_agent2 x_46_25_agent2 x_46_34_agent2 x_46_42_agent2 x_46_60_agent2
 x_47_55_agent2 x_52_55_agent2 x_53_31_agent2 x_55_44_agent2 x_55_47_agent2
 x_55_52_agent2 x_60_46_agent2 y_12_agent0 y_14_agent0 y_18_agent0
 y_25_agent0 y_27_agent0 y_31_agent0 y_34_agent0 y_42_agent0 y_44_agent0
 y_47_agent0 y_52_agent0 y_53_agent0 y_55_agent0 y_60_agent0 y_61_agent0
 y_62_agent0 y_63_agent0 y_12_agent1 y_14_agent1 y_18_agent1 y_25_agent1
 y_27_agent1 y_31_agent1 y_34_agent1 y_42_agent1 y_44_agent1 y_46_agent1
 y_47_agent1 y_52_agent1 y_53_agent1 y_60_agent1 y_61_agent1 y_62_agent1
 y_63_agent1 y_12_agent2 y_14_agent2 y_18_agent2 y_25_agent2 y_27_agent2
 y_34_agent2 y_42_agent2 y_44_agent2 y_46_agent2 y_47_agent2 y_52_agent2
 y_53_agent2 y_55_agent2 y_60_agent2 y_61_agent2 y_62_agent2 y_63_agent2
 z_5_12_agent0 z_5_14_agent0 z_5_18_agent0 z_5_25_agent0 z_5_27_agent0
 z_5_34_agent0 z_5_42_agent0 z_5_44_agent0 z_5_47_agent0 z_5_52_agent0
 z_5_53_agent0 z_5_60_agent0 z_5_12_agent1 z_5_14_agent1 z_5_18_agent1
 z_5_25_agent1 z_5_27_agent1 z_5_34_agent1 z_5_42_agent1 z_5_44_agent1
 z_5_47_agent1 z_5_52_agent1 z_5_53_agent1 z_5_60_agent1 z_5_12_agent2
 z_5_14_agent2 z_5_18_agent2 z_5_25_agent2 z_5_27_agent2 z_5_34_agent2
 z_5_42_agent2 z_5_44_agent2 z_5_47_agent2 z_5_52_agent2 z_5_53_agent2
 z_5_60_agent2
End
