\ Model multi_agent_many_to_many
\ LP format - for model browsing. Use MPS format to capture full model detail.
\ Signature: 0x1db11004b7e852f5
Maximize multi-objectives
  target_directed_reward: Priority=2 Weight=1 AbsTol=0 RelTol=0
   0 u_61_agent0 + 0.2 z_3_2_agent0 + 0.8 z_3_58_agent0
  target_directed_route_cost: Priority=1 Weight=1 AbsTol=0 RelTol=0
   - 0.0845310776020596 x_2_19_agent0 - 0.0845310776020596 x_19_2_agent0
   - 0.0835932328061787 x_19_58_agent0 - 0.0835932328061787 x_58_19_agent0
   + 0.0835932328061787 Constant1
Subject To
 depart_agent0: x_19_2_agent0 + x_19_58_agent0 = 1
 first_hop_vp_agent0: x_19_2_agent0 + x_19_58_agent0 = 1
 first_hop_grounded_vv_agent0: x_19_2_agent0 + x_19_58_agent0 = 1
 no_return_agent0: x_2_19_agent0 + x_58_19_agent0 = 0
 flow_in_2_agent0: x_19_2_agent0 - y_2_agent0 = 0
 flow_out_2_agent0: x_2_19_agent0 - y_2_agent0 <= 0
 flow_in_58_agent0: x_19_58_agent0 - y_58_agent0 = 0
 flow_out_58_agent0: x_58_19_agent0 - y_58_agent0 <= 0
 flow_in_61_agent0: - y_61_agent0 = 0
 flow_out_61_agent0: - y_61_agent0 <= 0
 target_reward_visit_3_2_agent0: - y_2_agent0 + z_3_2_agent0 <= 0
 target_reward_visit_3_58_agent0: - y_58_agent0 + z_3_58_agent0 <= 0
 mtz_2_19_agent0: 4 x_2_19_agent0 + u_2_agent0 - u_19_agent0 <= 3
 mtz_19_2_agent0: 4 x_19_2_agent0 - u_2_agent0 + u_19_agent0 <= 3
 mtz_19_58_agent0: 4 x_19_58_agent0 + u_19_agent0 - u_58_agent0 <= 3
 mtz_58_19_agent0: 4 x_58_19_agent0 - u_19_agent0 + u_58_agent0 <= 3
 target_reward_unique_3: z_3_2_agent0 + z_3_58_agent0 <= 1
 target_directed_agent_assignment_agent0: z_3_2_agent0 + z_3_58_agent0
   >= 1
Bounds
 1 <= u_2_agent0 <= 4
 1 <= u_19_agent0 <= 4
 1 <= u_58_agent0 <= 4
 1 <= u_61_agent0 <= 4
 Constant1 = 1
Binaries
 x_2_19_agent0 x_19_2_agent0 x_19_58_agent0 x_58_19_agent0 y_2_agent0
 y_58_agent0 y_61_agent0 z_3_2_agent0 z_3_58_agent0
End
