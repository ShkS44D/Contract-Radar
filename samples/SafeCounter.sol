// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

// Minimal clean example; a clean static scan is not proof of complete safety.
contract SafeCounter {
    mapping(address => uint256) public counts;
    event CountChanged(address indexed account, uint256 count);

    function increment() external {
        counts[msg.sender] += 1;
        emit CountChanged(msg.sender, counts[msg.sender]);
    }
}
