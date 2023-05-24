#include <algorithm>
#include <exception>
#include <filesystem>
#include <string>
#include <utility>

#include <binary_io/any_stream.hpp>
#include <binary_io/file_stream.hpp>
#include <bsa/bsa.hpp>

namespace
{
	[[nodiscard]] auto open_file(const std::filesystem::path& a_path)
		-> binary_io::any_ostream
	{
		std::filesystem::create_directories(a_path.parent_path());
		return binary_io::any_ostream(
			std::in_place_type<binary_io::file_ostream>,
			a_path);
	}

	void extract_tes3(
		const std::filesystem::path& a_input,
		const std::filesystem::path& a_output)
	{
		bsa::tes3::archive bsa;
		bsa.read(a_input);

		for (const auto& [key, file] : bsa) {
			auto out = open_file(a_output / key.name());
			file.write(out);
		}
	}

	void extract_tes4(
		const std::filesystem::path& a_input,
		const std::filesystem::path& a_output)
	{
		bsa::tes4::archive bsa;
		const auto format = bsa.read(a_input);

		for (auto& dir : bsa) {
			for (auto& file : dir.second) {
				auto out = open_file(a_output / dir.first.name() / file.first.name());
				file.second.write(out, format);
			}
		}
	}

	void extract_fo4(
		const std::filesystem::path& a_input,
		const std::filesystem::path& a_output)
	{
		bsa::fo4::archive ba2;
		const auto format = ba2.read(a_input);

		for (auto& [key, file] : ba2) {
			auto out = open_file(a_output / key.name());
			file.write(out, format);
		}
	}

	thread_local std::string last_error;
}

extern "C" __declspec(dllexport) int __cdecl extract_archive(
	const char* a_archive,
	const char* a_destination) noexcept
{
	try {
		const auto archive = std::filesystem::path(reinterpret_cast<const char8_t*>(a_archive));
		const auto destination = std::filesystem::path(reinterpret_cast<const char8_t*>(a_destination));
		const auto format = bsa::guess_file_format(archive).value();

		switch (format) {
		case bsa::file_format::tes3:
			extract_tes3(archive, destination);
			break;
		case bsa::file_format::tes4:
			extract_tes4(archive, destination);
			break;
		case bsa::file_format::fo4:
			extract_fo4(archive, destination);
			break;
		}
	} catch (const std::exception& a_err) {
		last_error = a_err.what();
		return -1;
	}

	return 0;
}

extern "C" [[nodiscard]] __declspec(dllexport) unsigned __cdecl get_last_error(
	char* a_destination,
	unsigned a_length) noexcept
{
	const auto error_length = static_cast<unsigned>(last_error.size()) + 1;
	if (a_destination == nullptr || a_length == 0) {
		return error_length;
	} else {
		const auto result_length = std::min(error_length, a_length);
		std::memcpy(a_destination, last_error.c_str(), result_length);
		return result_length;
	}
}
