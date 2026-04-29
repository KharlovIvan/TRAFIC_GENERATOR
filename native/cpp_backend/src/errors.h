#pragma once
#include <stdexcept>
#include <string>

namespace trafic {

class NativeError : public std::runtime_error {
public:
    enum class Kind { Config, Serialization, Transport };

    NativeError(Kind kind, const std::string& msg)
        : std::runtime_error(msg), kind_(kind) {}

    Kind kind() const noexcept { return kind_; }

private:
    Kind kind_;
};

} // namespace trafic
